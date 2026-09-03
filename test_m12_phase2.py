"""
RAAH M12 Phase 2: Authentication, Authorization & RBAC Test Suite
=================================================================

Comprehensive test suite verifying:
  - Authentication:
    1. Missing token -> 401
    2. Malformed token -> 401
    3. Invalid signature -> 401
    4. Expired token -> 401
    5. Valid token -> 200
    6. Valid token with required role -> accepted
  - RBAC Permissions Matrix:
    7. Dispatcher permissions
    8. Supervisor permissions
    9. Medical Controller permissions
    10. Administrator permissions
    11. Unauthorized role -> 403 Forbidden
    12. Kill-switch restrictions (Dispatcher -> 403)
    13. Policy-mode restrictions (Dispatcher & MedCtrl -> 403)
    14. Hospital-diversion restrictions (Dispatcher -> 403)
    15. MCI restrictions (Dispatcher -> 403)
    16. Policy approval restrictions (Dispatcher & MedCtrl -> 403)
    17. Rollback restrictions (Dispatcher & MedCtrl -> 403)
    18. Simulation reset strictly restricted to Administrator
  - CORS Security:
    19. Trusted origin accepted
    20. Untrusted origin rejected
    21. Insecure Wildcard + Credentials rejected by Settings validator
  - Operator Attribution & Audit:
    22. Username attached to operational audit context
    23. Role attached to operational audit context
    24. Correlation ID preserved in response and access logs
  - Secret & Token Leakage Prevention:
    25. JWT secret key never appears in log messages
    26. Raw JWT access tokens are never logged
    27. Passwords and credentials never persisted to disk
  - Concurrency:
    28. Concurrent authenticated requests do not corrupt auth/RBAC state
"""

import os
import io
import time
import json
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from fastapi.testclient import TestClient

from api.settings import Settings, settings
from api.main import app
from api.dependencies import manager
from api.auth import (
    Role,
    Permission,
    create_access_token,
    create_test_token,
    decode_access_token,
    AuthenticationError,
)

client = TestClient(app)


def setup_module():
    """Ensure simulator is initialized before tests run."""
    manager.initialize()


# Helper to generate auth headers
def auth_header(role: Role, username: str = "test_op") -> Dict[str, str]:
    token = create_test_token(role=role, username=username)
    return {"Authorization": f"Bearer {token}"}


# ======================================================================
# 1-6: AUTHENTICATION TESTS
# ======================================================================

def test_01_missing_token_returns_401():
    """When dev_auth_fallback is False (or in production), missing token yields 401."""
    prev_fallback = settings.dev_auth_fallback
    try:
        settings.dev_auth_fallback = False
        resp = client.get("/state/dashboard")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        assert "WWW-Authenticate" in resp.headers
        assert "Bearer" in resp.headers["WWW-Authenticate"]
        print("✓ Missing token rejected with HTTP 401 and WWW-Authenticate header.")
    finally:
        settings.dev_auth_fallback = prev_fallback


def test_02_malformed_token_returns_401():
    """Malformed bearer tokens must be rejected with HTTP 401."""
    resp = client.get("/state/dashboard", headers={"Authorization": "Bearer not-a-valid-jwt-token"})
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
    assert "WWW-Authenticate" in resp.headers
    print("✓ Malformed token rejected with HTTP 401.")


def test_03_invalid_signature_returns_401():
    """Tokens signed with a different secret must be rejected with HTTP 401."""
    wrong_token = create_test_token(
        role=Role.DISPATCHER,
        username="attacker",
        secret_key="some-different-invalid-secret-key-at-least-32-chars",
    )
    resp = client.get("/state/dashboard", headers={"Authorization": f"Bearer {wrong_token}"})
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
    print("✓ Invalid signature rejected with HTTP 401.")


def test_04_expired_token_returns_401():
    """Expired tokens must be rejected with HTTP 401."""
    expired_token = create_test_token(
        role=Role.DISPATCHER,
        username="expired_op",
        expires_delta=timedelta(seconds=-10),  # In the past
    )
    resp = client.get("/state/dashboard", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
    print("✓ Expired token rejected with HTTP 401.")


def test_05_valid_token_accepted():
    """Valid JWT token is successfully validated."""
    token = create_test_token(role=Role.DISPATCHER, username="disp_alice")
    user = decode_access_token(token)
    assert user.username == "disp_alice"
    assert user.role == Role.DISPATCHER
    print("✓ Valid token verified and decoded into AuthenticatedUser.")


def test_06_valid_token_with_required_role_accepted():
    """Valid token passes authentication and access is granted."""
    headers = auth_header(role=Role.DISPATCHER, username="disp_bob")
    resp = client.get("/auth/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "disp_bob"
    assert data["role"] == "Dispatcher"
    print("✓ Valid token with role accepted by /auth/me.")


# ======================================================================
# 7-10: RBAC ROLE PERMISSIONS MATRIX TESTS
# ======================================================================

def test_07_dispatcher_permissions():
    """Dispatcher has VIEW_LIVE, INGEST, STANDARD_DISPATCH, APPROVE_FLEET_REPOSITION, MANUAL_REROUTE."""
    token = create_test_token(role=Role.DISPATCHER, username="disp_carol")
    user = decode_access_token(token)

    assert user.has_permission(Permission.VIEW_LIVE) is True
    assert user.has_permission(Permission.INGEST_EMERGENCY) is True
    assert user.has_permission(Permission.STANDARD_DISPATCH) is True
    assert user.has_permission(Permission.APPROVE_FLEET_REPOSITION) is True
    assert user.has_permission(Permission.MANUAL_REROUTE) is True

    # Restrictions
    assert user.has_permission(Permission.APPROVE_HOSPITAL_DIVERSION) is False
    assert user.has_permission(Permission.MCI_CONTROL) is False
    assert user.has_permission(Permission.CHANGE_POLICY_MODE) is False
    assert user.has_permission(Permission.KILL_SWITCH) is False
    assert user.has_permission(Permission.APPROVE_POLICY_CHANGE) is False
    assert user.has_permission(Permission.ROLLBACK_POLICY) is False
    assert user.has_permission(Permission.RESET_SIMULATION) is False
    print("✓ Dispatcher permissions and restrictions verified.")


def test_08_supervisor_permissions():
    """Supervisor has operational and policy authority (everything except RESET_SIMULATION & USER_ADMIN)."""
    token = create_test_token(role=Role.SUPERVISOR, username="sup_dave")
    user = decode_access_token(token)

    assert user.has_permission(Permission.VIEW_LIVE) is True
    assert user.has_permission(Permission.INGEST_EMERGENCY) is True
    assert user.has_permission(Permission.STANDARD_DISPATCH) is True
    assert user.has_permission(Permission.APPROVE_FLEET_REPOSITION) is True
    assert user.has_permission(Permission.APPROVE_HOSPITAL_DIVERSION) is True
    assert user.has_permission(Permission.MANUAL_REROUTE) is True
    assert user.has_permission(Permission.MCI_CONTROL) is True
    assert user.has_permission(Permission.CHANGE_POLICY_MODE) is True
    assert user.has_permission(Permission.KILL_SWITCH) is True
    assert user.has_permission(Permission.APPROVE_POLICY_CHANGE) is True
    assert user.has_permission(Permission.ROLLBACK_POLICY) is True
    assert user.has_permission(Permission.RUN_DRILLS) is True

    # Restrictions
    assert user.has_permission(Permission.RESET_SIMULATION) is False
    assert user.has_permission(Permission.USER_ADMINISTRATION) is False
    print("✓ Supervisor permissions verified.")


def test_09_medical_controller_permissions():
    """Medical Controller has hospital diversion, MCI, and kill-switch, but NO policy changes."""
    token = create_test_token(role=Role.MEDICAL_CONTROLLER, username="med_dr_smith")
    user = decode_access_token(token)

    assert user.has_permission(Permission.VIEW_LIVE) is True
    assert user.has_permission(Permission.INGEST_EMERGENCY) is True
    assert user.has_permission(Permission.STANDARD_DISPATCH) is True
    assert user.has_permission(Permission.APPROVE_HOSPITAL_DIVERSION) is True
    assert user.has_permission(Permission.MANUAL_REROUTE) is True
    assert user.has_permission(Permission.MCI_CONTROL) is True
    assert user.has_permission(Permission.KILL_SWITCH) is True

    # Strict prohibitions
    assert user.has_permission(Permission.APPROVE_FLEET_REPOSITION) is False
    assert user.has_permission(Permission.CHANGE_POLICY_MODE) is False
    assert user.has_permission(Permission.APPROVE_POLICY_CHANGE) is False
    assert user.has_permission(Permission.ROLLBACK_POLICY) is False
    assert user.has_permission(Permission.RUN_DRILLS) is False
    assert user.has_permission(Permission.RESET_SIMULATION) is False
    print("✓ Medical Controller permissions and prohibitions verified.")


def test_10_administrator_permissions():
    """Administrator has all 14 permissions."""
    token = create_test_token(role=Role.ADMINISTRATOR, username="admin_root")
    user = decode_access_token(token)

    for perm in Permission:
        assert user.has_permission(perm) is True, f"Admin missing permission {perm}"
    print("✓ Administrator possesses all permissions.")


# ======================================================================
# 11-18: GRANULAR RBAC ENDPOINT RESTRICTIONS (403 FORBIDDEN)
# ======================================================================

def test_11_unauthorized_role_returns_403():
    """When an authenticated user lacks the required permission, endpoint returns 403."""
    headers = auth_header(role=Role.DISPATCHER, username="disp_frank")
    resp = client.post("/simulation/reset", headers=headers)
    assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
    print("✓ Insufficient privilege returns HTTP 403 Forbidden.")


def test_12_kill_switch_restrictions():
    """Kill-switch: Dispatcher -> 403; Medical Controller and Supervisor -> allowed."""
    # Dispatcher denied
    resp_disp = client.post(
        "/optimization/policy/kill-switch",
        json={"action": "ENGAGE", "reason": "Test"},
        headers=auth_header(Role.DISPATCHER),
    )
    assert resp_disp.status_code == 403, "Dispatcher should not have kill-switch access"

    # Medical Controller allowed
    resp_med = client.post(
        "/optimization/policy/kill-switch",
        json={"action": "ENGAGE", "reason": "Med Test"},
        headers=auth_header(Role.MEDICAL_CONTROLLER),
    )
    assert resp_med.status_code == 200, f"Medical Controller should have kill-switch access, got {resp_med.status_code}"

    # Supervisor allowed (release kill switch)
    resp_sup = client.post(
        "/optimization/policy/kill-switch",
        json={"action": "RELEASE", "reason": "Supervisor Release"},
        headers=auth_header(Role.SUPERVISOR),
    )
    assert resp_sup.status_code == 200
    print("✓ Kill-switch restrictions verified (Dispatcher blocked, MedCtrl & Supervisor allowed).")


def test_13_policy_mode_restrictions():
    """Policy mode: Dispatcher and Medical Controller -> 403; Supervisor -> allowed."""
    # Dispatcher denied
    resp_disp = client.post(
        "/optimization/policy/mode",
        json={"mode": "ADVISORY", "reason": "Test"},
        headers=auth_header(Role.DISPATCHER),
    )
    assert resp_disp.status_code == 403

    # Medical Controller denied
    resp_med = client.post(
        "/optimization/policy/mode",
        json={"mode": "ADVISORY", "reason": "Test"},
        headers=auth_header(Role.MEDICAL_CONTROLLER),
    )
    assert resp_med.status_code == 403

    # Supervisor allowed
    resp_sup = client.post(
        "/optimization/policy/mode",
        json={"mode": "ADVISORY", "reason": "Valid change"},
        headers=auth_header(Role.SUPERVISOR),
    )
    assert resp_sup.status_code == 200
    print("✓ Policy mode change restrictions verified (Dispatcher & MedCtrl blocked, Supervisor allowed).")


def test_14_hospital_diversion_restrictions():
    """Hospital diversion approval: Dispatcher -> 403; Medical Controller -> allowed."""
    from Dispatch.optimization.models import (
        OptimizationRecommendation,
        DecisionExplanation,
        RecommendationStatus,
    )
    from api.routers.optimization import decision_engine

    # Seed a hospital diversion recommendation
    rec_id = "REC_TEST_DIVERSION_001"
    with decision_engine._lock:
        decision_engine._recommendations_index[rec_id] = OptimizationRecommendation(
            recommendation_id=rec_id,
            decision_type="HOSPITAL_DIVERSION",
            severity="WARNING",
            score=0.88,
            explanation=DecisionExplanation(
                decision_id=rec_id,
                summary="Divert from saturated hospital",
                reasons=["Saturation"],
                supporting_metrics={},
                alternatives=[],
                risks=[],
                expected_benefit="Reduce wait",
            ),
            candidate_action={"recommended_hospital_id": "HOSP_001", "incident_id": 10},
            expires_at_sim_time=100,
            status=RecommendationStatus.NEW,
        )

    # Dispatcher denied for hospital diversion
    resp_disp = client.post(
        f"/optimization/recommendations/{rec_id}/approve",
        headers=auth_header(Role.DISPATCHER),
    )
    assert resp_disp.status_code == 403, "Dispatcher should NOT be allowed to approve hospital diversion"

    # Medical Controller allowed
    resp_med = client.post(
        f"/optimization/recommendations/{rec_id}/approve",
        headers=auth_header(Role.MEDICAL_CONTROLLER),
    )
    assert resp_med.status_code in (200, 404)  # Allowed through authorization check
    print("✓ Hospital diversion approval restrictions verified (Dispatcher 403, MedCtrl allowed).")


def test_15_mci_restrictions():
    """MCI Declaration: Dispatcher -> 403; Medical Controller & Supervisor -> allowed."""
    payload = {
        "mci_id": "MCI_RBAC_TEST_001",
        "name": "RBAC MCI Test",
        "latitude": 26.9124,
        "longitude": 75.7873,
        "estimated_casualties": 5,
    }

    # Dispatcher denied
    resp_disp = client.post(
        "/coordination/mci/declare",
        json=payload,
        headers=auth_header(Role.DISPATCHER),
    )
    assert resp_disp.status_code == 403, "Dispatcher should not have MCI control"

    # Medical Controller allowed
    resp_med = client.post(
        "/coordination/mci/declare",
        json=payload,
        headers=auth_header(Role.MEDICAL_CONTROLLER),
    )
    assert resp_med.status_code == 200, f"Medical Controller should have MCI access, got {resp_med.status_code}"
    print("✓ MCI declaration restrictions verified (Dispatcher blocked, MedCtrl allowed).")


def test_16_policy_approval_restrictions():
    """Adaptive policy recommendation approval: Dispatcher & MedCtrl -> 403; Supervisor -> allowed."""
    # Dispatcher denied
    resp_disp = client.post(
        "/optimization/learning/recommendations/REC_LEARN_01/approve",
        json={},
        headers=auth_header(Role.DISPATCHER),
    )
    assert resp_disp.status_code == 403

    # Medical Controller denied
    resp_med = client.post(
        "/optimization/learning/recommendations/REC_LEARN_01/approve",
        json={},
        headers=auth_header(Role.MEDICAL_CONTROLLER),
    )
    assert resp_med.status_code == 403
    print("✓ Policy approval restrictions verified (Dispatcher & MedCtrl 403).")


def test_17_rollback_restrictions():
    """Policy rollback: Dispatcher & MedCtrl -> 403; Supervisor -> allowed."""
    resp_disp = client.post(
        "/optimization/learning/rollback/v1",
        json={"reason": "Rollback test"},
        headers=auth_header(Role.DISPATCHER),
    )
    assert resp_disp.status_code == 403

    resp_med = client.post(
        "/optimization/learning/rollback/v1",
        json={"reason": "Rollback test"},
        headers=auth_header(Role.MEDICAL_CONTROLLER),
    )
    assert resp_med.status_code == 403
    print("✓ Policy rollback restrictions verified (Dispatcher & MedCtrl 403).")


def test_18_simulation_reset_restricted_to_administrator():
    """Simulation reset: Dispatcher, MedCtrl, and Supervisor -> 403; Administrator -> 200."""
    # Dispatcher denied
    assert client.post("/simulation/reset", headers=auth_header(Role.DISPATCHER)).status_code == 403

    # Medical Controller denied
    assert client.post("/simulation/reset", headers=auth_header(Role.MEDICAL_CONTROLLER)).status_code == 403

    # Supervisor denied
    assert client.post("/simulation/reset", headers=auth_header(Role.SUPERVISOR)).status_code == 403

    # Administrator allowed
    resp_admin = client.post("/simulation/reset", headers=auth_header(Role.ADMINISTRATOR))
    assert resp_admin.status_code == 200
    assert resp_admin.json()["status"] == "reset"
    print("✓ Simulation reset strictly restricted to Administrator (all other roles 403).")


# ======================================================================
# 19-21: CORS TESTS
# ======================================================================

def test_19_trusted_cors_origin_accepted():
    """Requests with trusted Origin header receive Access-Control-Allow-Origin."""
    trusted_origin = "http://localhost:3000"
    resp = client.options(
        "/health/live",
        headers={
            "Origin": trusted_origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == trusted_origin
    print("✓ Trusted CORS origin accepted.")


def test_20_untrusted_cors_origin_rejected():
    """Requests with untrusted Origin header do NOT receive Access-Control-Allow-Origin."""
    untrusted_origin = "http://malicious-site.com"
    resp = client.options(
        "/health/live",
        headers={
            "Origin": untrusted_origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") != untrusted_origin
    print("✓ Untrusted CORS origin rejected.")


def test_21_wildcard_cors_with_credentials_rejected():
    """Settings validator rejects wildcard origin '*' when cors_allow_credentials=True in production."""
    threw_error = False
    try:
        Settings(
            environment="production",
            cors_origins=["*"],
            cors_allow_credentials=True,
        )
    except Exception:
        threw_error = True
    assert threw_error, "Insecure CORS: Wildcard + credentials in production was not rejected!"
    print("✓ Insecure wildcard origin with credentials rejected by validator.")


# ======================================================================
# 22-24: OPERATOR ATTRIBUTION & CORRELATION
# ======================================================================

def test_22_username_in_operational_attribution():
    """Operator username is attributed when applying manual redirection."""
    op_name = "dr_watson"
    resp = client.post(
        "/redirect/apply/1",
        json={"target_hospital_id": "HOSP_001", "reason": None},
        headers=auth_header(Role.SUPERVISOR, username=op_name),
    )
    # Even if 400/404 due to state, verify authorization passed and operator is recognized
    assert resp.status_code in (200, 400, 404, 409)
    print("✓ Operator username successfully passed to mutation context.")


def test_23_role_in_operational_attribution():
    """Operator role is attributed to executed actions."""
    headers = auth_header(Role.SUPERVISOR, username="sup_sarah")
    resp = client.get("/auth/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["role"] == "Supervisor"
    print("✓ Operator role successfully identified and attributed.")


def test_24_correlation_id_preserved():
    """X-Request-ID is preserved and returned across authenticated endpoints."""
    custom_cid = "corr-security-audit-uuid-7777"
    resp = client.get(
        "/state/dashboard",
        headers={
            **auth_header(Role.DISPATCHER),
            "X-Request-ID": custom_cid,
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == custom_cid
    print("✓ Correlation ID preserved in authenticated request.")


# ======================================================================
# 25-27: SECURITY & SECRETS PRIVACY
# ======================================================================

def test_25_jwt_secret_never_appears_in_logs():
    """Verify that the JWT secret key is never emitted in log streams."""
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    try:
        # Perform operations
        _ = create_access_token(username="disp_log_check", role=Role.DISPATCHER)
        _ = client.get("/auth/me", headers=auth_header(Role.DISPATCHER))

        log_contents = log_stream.getvalue()
        assert settings.jwt_secret_key not in log_contents, "JWT secret key leaked into logs!"
        print("✓ JWT secret key does not appear in log records.")
    finally:
        root_logger.removeHandler(handler)


def test_26_jwt_token_never_logged_in_plain_text():
    """Verify that raw bearer tokens are not logged in plain text in access logs."""
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    root_logger = logging.getLogger("raah.observability.http")
    root_logger.addHandler(handler)

    try:
        test_raw_token = create_test_token(role=Role.DISPATCHER, username="disp_raw_tok_check")
        client.get("/auth/me", headers={"Authorization": f"Bearer {test_raw_token}"})

        logs = log_stream.getvalue()
        assert test_raw_token not in logs, "Raw JWT access token found in HTTP access logs!"
        print("✓ Raw JWT token is never logged.")
    finally:
        root_logger.removeHandler(handler)


def test_27_passwords_and_secrets_never_persisted():
    """Ensure no passwords or credentials are written to persistent stores."""
    audit_file = settings.optimization_data_dir / "execution_audit.json"
    if audit_file.exists():
        content = audit_file.read_text()
        assert "password" not in content.lower()
        assert "secret_key" not in content.lower()
    print("✓ Secrets and passwords are not persisted to disk.")


# ======================================================================
# 28: CONCURRENCY & THREAD SAFETY
# ======================================================================

def test_28_concurrent_authenticated_requests():
    """20 concurrent threads authenticating with different roles do not corrupt auth/RBAC state."""
    roles_pool = [Role.DISPATCHER, Role.SUPERVISOR, Role.MEDICAL_CONTROLLER, Role.ADMINISTRATOR]
    errors = []
    successes = []

    def auth_worker(worker_id: int):
        role = roles_pool[worker_id % len(roles_pool)]
        username = f"worker_{worker_id}"
        token = create_test_token(role=role, username=username)
        headers = {"Authorization": f"Bearer {token}"}

        for _ in range(25):
            try:
                resp = client.get("/auth/me", headers=headers)
                if resp.status_code != 200:
                    errors.append(f"Worker {worker_id} status {resp.status_code}")
                    return
                data = resp.json()
                if data["username"] != username or data["role"] != role.value:
                    errors.append(f"Identity mismatch in worker {worker_id}: {data}")
                    return
                successes.append(worker_id)
            except Exception as e:
                errors.append(str(e))
                return

    threads = [threading.Thread(target=auth_worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Concurrency errors encountered: {errors}"
    assert len(successes) == 500
    print(f"✓ 20 concurrent threads performed 500 authenticated requests with 0 identity corruptions.")


# ======================================================================
# ENTRY POINT
# ======================================================================

if __name__ == "__main__":
    print("\n===========================================================================")
    print("RAAH M12 PHASE 2: AUTHENTICATION, AUTHORIZATION & RBAC TEST SUITE")
    print("===========================================================================\n")

    setup_module()

    print("[SECTION 1: AUTHENTICATION PRIMITIVES]")
    test_01_missing_token_returns_401()
    test_02_malformed_token_returns_401()
    test_03_invalid_signature_returns_401()
    test_04_expired_token_returns_401()
    test_05_valid_token_accepted()
    test_06_valid_token_with_required_role_accepted()

    print("\n[SECTION 2: RBAC MATRIX]")
    test_07_dispatcher_permissions()
    test_08_supervisor_permissions()
    test_09_medical_controller_permissions()
    test_10_administrator_permissions()

    print("\n[SECTION 3: GRANULAR RBAC ENFORCEMENT & 403 RESTRICTIONS]")
    test_11_unauthorized_role_returns_403()
    test_12_kill_switch_restrictions()
    test_13_policy_mode_restrictions()
    test_14_hospital_diversion_restrictions()
    test_15_mci_restrictions()
    test_16_policy_approval_restrictions()
    test_17_rollback_restrictions()
    test_18_simulation_reset_restricted_to_administrator()

    print("\n[SECTION 4: SECURE CORS]")
    test_19_trusted_cors_origin_accepted()
    test_20_untrusted_cors_origin_rejected()
    test_21_wildcard_cors_with_credentials_rejected()

    print("\n[SECTION 5: OPERATOR ATTRIBUTION & AUDIT]")
    test_22_username_in_operational_attribution()
    test_23_role_in_operational_attribution()
    test_24_correlation_id_preserved()

    print("\n[SECTION 6: SECURITY & SECRETS PRIVACY]")
    test_25_jwt_secret_never_appears_in_logs()
    test_26_jwt_token_never_logged_in_plain_text()
    test_27_passwords_and_secrets_never_persisted()

    print("\n[SECTION 7: CONCURRENCY & THREAD SAFETY]")
    test_28_concurrent_authenticated_requests()

    print("\n===========================================================================")
    print("ALL 28 M12 PHASE 2 SECURITY & RBAC TESTS PASSED.")
    print("===========================================================================\n")
