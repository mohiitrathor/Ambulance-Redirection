"""
RAAH Scenario & Replay Storage (M10 Phase 1)
===========================================

Filesystem-backed JSON storage for scenario definitions and replay archives.
Features atomic file writes, crash resilience, and clean isolation from SQLite persistence.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any

from .models import ScenarioDefinition, ReplayArtifact, RunMetadata

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO_DIR = ROOT / "data" / "scenarios"
DEFAULT_REPLAY_DIR = ROOT / "data" / "replays"


def _atomic_write_json(file_path: Path, data: Dict[str, Any]):
    """Atomically write a JSON serializable dict via a temporary file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, file_path)


class ScenarioStore:
    """Manages persistence and retrieval of ScenarioDefinition specifications."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.dir = Path(storage_dir or DEFAULT_SCENARIO_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)

    def save(self, scenario: ScenarioDefinition) -> str:
        """Persist scenario definition atomically."""
        sid = str(scenario.scenario_id)
        path = self.dir / f"{sid}.json"
        _atomic_write_json(path, scenario.to_dict())
        return sid

    def get(self, scenario_id: str) -> Optional[ScenarioDefinition]:
        """Load scenario definition by ID."""
        path = self.dir / f"{scenario_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ScenarioDefinition.from_dict(data)
        except Exception:
            return None

    def list(self) -> List[ScenarioDefinition]:
        """Return all available scenarios sorted by ID."""
        scenarios = []
        for p in self.dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                scenarios.append(ScenarioDefinition.from_dict(data))
            except Exception:
                continue
        scenarios.sort(key=lambda s: s.scenario_id)
        return scenarios

    def delete(self, scenario_id: str) -> bool:
        """Delete scenario file."""
        path = self.dir / f"{scenario_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False


class ReplayStore:
    """Manages persistence and retrieval of portable ReplayArtifact records."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.dir = Path(storage_dir or DEFAULT_REPLAY_DIR)
        self.dir.mkdir(parents=True, exist_ok=True)

    def save(self, replay: ReplayArtifact) -> str:
        """Persist replay artifact atomically."""
        rid = str(replay.run_metadata.run_id)
        path = self.dir / f"{rid}.json"
        _atomic_write_json(path, replay.to_dict())
        return rid

    def get(self, run_id: str) -> Optional[ReplayArtifact]:
        """Load replay artifact by run ID."""
        path = self.dir / f"{run_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return ReplayArtifact.from_dict(data)
        except Exception:
            return None

    def list_metadata(self) -> List[RunMetadata]:
        """Return metadata summary for all recorded replays."""
        metas = []
        for p in self.dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                metas.append(RunMetadata.from_dict(data["run_metadata"]))
            except Exception:
                continue
        metas.sort(key=lambda m: m.created_at, reverse=True)
        return metas

    def delete(self, run_id: str) -> bool:
        """Delete replay artifact file."""
        path = self.dir / f"{run_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False
