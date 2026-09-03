"""
RAAH State Recovery Engine
==========================

Orchestrates startup state recovery from durable storage into DispatchState.
Validates schema versions, cryptographic checksums, and domain invariants.
Provides safe fallback mechanisms when checkpoints are corrupted or incompatible.
"""

import logging
import time
from typing import Tuple, Optional, Dict, Any

from state import DispatchState
from api.persistence.interface import (
    StatePersistenceStore,
    CheckpointRecord,
    PersistenceError,
    CorruptCheckpointError,
    IncompatibleSchemaError,
    CorruptStateError,
    DatabaseUnavailableError,
)
from api.persistence.serializer import deserialize_dispatch_state

logger = logging.getLogger("raah.persistence.recovery")


class RecoveryStatus:
    RECOVERED = "RECOVERED"
    CLEAN_START = "CLEAN_START"
    FALLBACK_CLEAN = "FALLBACK_CLEAN"
    DISABLED = "DISABLED"
    FAILED = "FAILED"


class StateRecoveryEngine:
    """
    Executes and audits state recovery operations.
    """

    @staticmethod
    def recover_state(
        store: StatePersistenceStore,
        fallback_to_clean: bool = True,
    ) -> Tuple[Optional[DispatchState], str, Optional[str], Optional[str]]:
        """
        Recover the latest valid DispatchState from persistent storage.

        Returns:
          (state, status, checkpoint_id, error_message)
          - If a valid checkpoint is restored: (DispatchState, "RECOVERED", cid, None)
          - If no checkpoints exist: (None, "CLEAN_START", None, None)
          - If checkpoint is corrupt and fallback is True: (None, "FALLBACK_CLEAN", cid, error_msg)
          - If unrecoverable and fallback is False: (None, "FAILED", cid, error_msg)
        """
        start_t = time.perf_counter()
        logger.info("Initiating state recovery sequence.")

        latest_record: Optional[CheckpointRecord] = None
        try:
            latest_record = store.load_latest_checkpoint()
        except DatabaseUnavailableError as db_err:
            err_msg = f"Persistence store unavailable during recovery: {db_err}"
            logger.error(err_msg)
            if fallback_to_clean:
                logger.warning("Falling back to clean initial state due to unavailable persistence store.")
                return None, RecoveryStatus.FALLBACK_CLEAN, None, err_msg
            return None, RecoveryStatus.FAILED, None, err_msg
        except (CorruptCheckpointError, IncompatibleSchemaError, CorruptStateError) as chk_err:
            err_msg = f"Latest checkpoint is corrupted: {chk_err}"
            logger.error(err_msg)
            if fallback_to_clean:
                logger.warning("Falling back to clean initial state due to corrupt checkpoint.")
                return None, RecoveryStatus.FALLBACK_CLEAN, None, err_msg
            return None, RecoveryStatus.FAILED, None, err_msg
        except Exception as ex:
            err_msg = f"Unexpected error reading latest checkpoint: {ex}"
            logger.error(err_msg)
            if fallback_to_clean:
                return None, RecoveryStatus.FALLBACK_CLEAN, None, err_msg
            return None, RecoveryStatus.FAILED, None, err_msg

        # Case 1: No previous checkpoint
        if latest_record is None:
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            logger.info("No existing state checkpoint found. Proceeding with clean initial state (%.2fms).", duration_ms)
            return None, RecoveryStatus.CLEAN_START, None, None

        # Case 2: Checkpoint found -> deserialize and validate
        cid = latest_record.checkpoint_id
        try:
            restored_state = deserialize_dispatch_state(latest_record.payload)
            duration_ms = (time.perf_counter() - start_t) * 1000.0

            logger.info(
                "State recovery successful: checkpoint_id=%s sim_time=%d incidents=%d ambulances=%d hospitals=%d duration=%.2fms",
                cid,
                restored_state.current_time,
                len(restored_state.incidents),
                len(restored_state.ambulances),
                len(restored_state.hospitals),
                duration_ms,
                extra={"checkpoint_id": cid, "duration_ms": duration_ms},
            )
            return restored_state, RecoveryStatus.RECOVERED, cid, None

        except (IncompatibleSchemaError, CorruptStateError, CorruptCheckpointError) as val_err:
            err_msg = f"Failed to reconstruct DispatchState from checkpoint '{cid}': {val_err}"
            logger.error(err_msg)
            if fallback_to_clean:
                logger.warning("Falling back to clean state following deserialization error for checkpoint '%s'.", cid)
                return None, RecoveryStatus.FALLBACK_CLEAN, cid, err_msg
            return None, RecoveryStatus.FAILED, cid, err_msg
        except Exception as unk_err:
            err_msg = f"Unexpected error deserializing checkpoint '{cid}': {unk_err}"
            logger.error(err_msg)
            if fallback_to_clean:
                return None, RecoveryStatus.FALLBACK_CLEAN, cid, err_msg
            return None, RecoveryStatus.FAILED, cid, err_msg
