from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timedelta, timezone
import uuid

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_action_token, hash_password
from app.create_admin import create_or_recover_admin
from app.models.audit import AuditLog
from app.models.user import ActionTokenType, RoleName, User, UserActionToken
from app.repositories import user_repo
from app.repositories.user_repo import get_role_by_name
from app.seed import seed_admin

_created_user_ids: list[uuid.UUID] = []


def _create_test_user(
    db: Session,
    role: RoleName,
    *,
    password: str = "StrongTestPass123!",
    is_active: bool = True,
    must_change_password: bool = False,
) -> tuple[User, str]:
    uid = uuid.uuid4().hex[:8]
    role_obj = get_role_by_name(db, role.value)
    user = User(
        email=f"day4-{role.value.lower()}-{uid}@example.com",
        full_name=f"Day4 {role.value}",
        password_hash=hash_password(password),
        role_id=role_obj.id,
        is_active=is_active,
        must_change_password=must_change_password,
        token_version=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _created_user_ids.append(user.id)
    return user, password


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture(autouse=True)
def cleanup_day4_test_users(db: Session) -> Generator[None, None, None]:
    yield
    db.rollback()
    while _created_user_ids:
        uid = _created_user_ids.pop()
        db.execute(delete(AuditLog).where(AuditLog.user_id == uid))
        db.execute(delete(AuditLog).where(AuditLog.entity_id == uid))
        db.execute(delete(UserActionToken).where(UserActionToken.user_id == uid))
        db.execute(delete(User).where(User.id == uid))
    db.commit()


@pytest.mark.parametrize(
    "endpoint_key,expected_by_role",
    [
        (
            "GET /api/v1/admin/users",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 403,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "POST /api/v1/admin/users/invite",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 403,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 201,
            },
        ),
        (
            "PATCH /api/v1/admin/users/{id}/role",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 403,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "POST /api/v1/admin/users/{id}/deactivate",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 403,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "POST /api/v1/admin/users/{id}/reactivate",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 403,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
        (
            "POST /api/v1/admin/users/{id}/reset-password",
            {
                None: 401,
                RoleName.FINANCE_EXECUTIVE: 403,
                RoleName.FINANCE_MANAGER: 403,
                RoleName.ACCOUNTS_AUDIT: 403,
                RoleName.SYSTEM_ADMIN: 200,
            },
        ),
    ],
)
def test_admin_users_endpoints_rbac_matrix(
    client: TestClient,
    db: Session,
    endpoint_key: str,
    expected_by_role: dict[RoleName | None, int],
) -> None:
    target, _ = _create_test_user(db, RoleName.ACCOUNTS_AUDIT)

    for role, expected_status in expected_by_role.items():
        if role is None:
            headers: dict[str, str] = {}
        else:
            actor, pwd = _create_test_user(db, role)
            headers = _login(client, actor.email, pwd)

        if endpoint_key == "GET /api/v1/admin/users":
            resp = client.get("/api/v1/admin/users", headers=headers)
        elif endpoint_key == "POST /api/v1/admin/users/invite":
            inv_email = f"matrix-inv-{uuid.uuid4().hex[:8]}@example.com"
            resp = client.post(
                "/api/v1/admin/users/invite",
                headers=headers,
                json={"email": inv_email, "role": "FINANCE_EXECUTIVE", "full_name": "Matrix Invitee"},
            )
            if resp.status_code == 201:
                _created_user_ids.append(uuid.UUID(resp.json()["data"]["user"]["id"]))
        elif endpoint_key == "PATCH /api/v1/admin/users/{id}/role":
            resp = client.patch(
                f"/api/v1/admin/users/{target.id}/role",
                headers=headers,
                json={"role": "FINANCE_EXECUTIVE"},
            )
        elif endpoint_key == "POST /api/v1/admin/users/{id}/deactivate":
            resp = client.post(f"/api/v1/admin/users/{target.id}/deactivate", headers=headers)
        elif endpoint_key == "POST /api/v1/admin/users/{id}/reactivate":
            resp = client.post(f"/api/v1/admin/users/{target.id}/reactivate", headers=headers)
        elif endpoint_key == "POST /api/v1/admin/users/{id}/reset-password":
            resp = client.post(f"/api/v1/admin/users/{target.id}/reset-password", headers=headers)
        else:
            raise AssertionError(f"Unhandled endpoint_key: {endpoint_key}")

        assert resp.status_code == expected_status, (
            f"{endpoint_key} with role={role}: expected {expected_status}, got {resp.status_code} ({resp.text})"
        )


def test_admin_bootstrap_skips_when_any_admin_exists_and_sets_must_change_when_none(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 1. Because at least one SYSTEM_ADMIN exists in DB, seed_admin must do nothing
    custom_admin, _ = _create_test_user(db, RoleName.SYSTEM_ADMIN, password="CustomPassword123!")
    original_hash = custom_admin.password_hash

    monkeypatch.setattr(settings, "ADMIN_EMAIL", custom_admin.email)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "DifferentBootPass999!")

    result = seed_admin(db, reset_password=False)
    assert result == "already existed"

    db.refresh(custom_admin)
    assert custom_admin.password_hash == original_hash
    assert custom_admin.must_change_password is False

    # 2. Simulate 0 SYSTEM_ADMINs in DB -> seed_admin creates new admin with must_change_password=True
    fresh_email = f"bootstrap-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(settings, "ADMIN_EMAIL", fresh_email)
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "FreshBootPass123!")
    monkeypatch.setattr(user_repo, "count_system_admins", lambda _db: 0)

    res2 = seed_admin(db, reset_password=False)
    assert res2 == "created"
    seeded = user_repo.get_user_by_email(db, fresh_email)
    assert seeded is not None
    _created_user_ids.append(seeded.id)
    assert seeded.role_name == RoleName.SYSTEM_ADMIN.value
    assert seeded.is_active is True
    assert seeded.must_change_password is True

    # 3. Test CLI create_or_recover_admin
    cli_email = f"cli-admin-{uuid.uuid4().hex[:8]}@example.com"
    with pytest.raises(ValueError, match="at least 12 characters"):
        create_or_recover_admin(db, email=cli_email, password="short")

    cli_user, action = create_or_recover_admin(
        db,
        email=cli_email,
        password="CliAdminRecoveryPass123!",
        full_name="CLI Admin",
    )
    _created_user_ids.append(cli_user.id)
    assert action == "created"
    assert cli_user.role_name == RoleName.SYSTEM_ADMIN.value
    assert cli_user.must_change_password is True


def test_forced_password_change_blocks_protected_routes_until_changed(
    client: TestClient,
    db: Session,
) -> None:
    user, old_pwd = _create_test_user(
        db,
        RoleName.FINANCE_EXECUTIVE,
        password="InitialTempPassword123!",
        must_change_password=True,
    )
    headers = _login(client, user.email, old_pwd)

    # 1. Allowed endpoints while must_change_password=True: /auth/me, /auth/change-password, /auth/logout
    me_resp = client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["data"]["must_change_password"] is True

    # 2. Other protected routes are blocked with 403 PASSWORD_CHANGE_REQUIRED
    for blocked_url in ("/api/v1/documents", "/api/v1/reviews", "/api/v1/search?q=invoice"):
        blocked_resp = client.get(blocked_url, headers=headers)
        assert blocked_resp.status_code == 403, blocked_resp.text
        assert blocked_resp.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    # 3. Password policy checks on /auth/change-password:
    # - Wrong current password -> 400
    wrong_cur = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": "WrongOldPassword123!", "new_password": "BrandNewValidPassword123!"},
    )
    assert wrong_cur.status_code == 400

    # - Too short (< 12 chars) -> 422
    short_pw = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": old_pwd, "new_password": "short"},
    )
    assert short_pw.status_code == 422

    # - Equal to old password -> 422
    same_pw = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": old_pwd, "new_password": old_pwd},
    )
    assert same_pw.status_code == 422
    assert same_pw.json()["error"]["code"] == "password_unchanged"

    # 4. Valid password change clears must_change_password and bumps token_version
    new_pwd = "UpdatedSecurePassword456!"
    ok_change = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": old_pwd, "new_password": new_pwd},
    )
    assert ok_change.status_code == 200, ok_change.text
    assert ok_change.json()["data"]["must_change_password"] is False

    # Old token is now invalidated because token_version was incremented
    old_token_check = client.get("/api/v1/auth/me", headers=headers)
    assert old_token_check.status_code == 401

    # Re-login with new password -> protected routes now return 200
    new_headers = _login(client, user.email, new_pwd)
    docs_resp = client.get("/api/v1/documents", headers=new_headers)
    assert docs_resp.status_code == 200


def test_invite_lifecycle_accept_resend_revoke_and_expiry(
    client: TestClient,
    db: Session,
) -> None:
    admin, admin_pwd = _create_test_user(db, RoleName.SYSTEM_ADMIN)
    admin_headers = _login(client, admin.email, admin_pwd)

    # 1. Cannot invite an email that already belongs to an active user (409)
    dup_invite = client.post(
        "/api/v1/admin/users/invite",
        headers=admin_headers,
        json={"email": admin.email, "role": "FINANCE_MANAGER"},
    )
    assert dup_invite.status_code == 409

    # 2. Invite a new user
    invite_email = f"invited-{uuid.uuid4().hex[:8]}@example.com"
    inv_resp = client.post(
        "/api/v1/admin/users/invite",
        headers=admin_headers,
        json={
            "email": invite_email,
            "role": "FINANCE_MANAGER",
            "full_name": "Invited Manager",
        },
    )
    assert inv_resp.status_code == 201, inv_resp.text
    inv_data = inv_resp.json()["data"]
    invited_user_id = uuid.UUID(inv_data["user"]["id"])
    _created_user_ids.append(invited_user_id)

    assert inv_data["user"]["status"] == "invited"
    assert inv_data["user"]["is_active"] is False
    assert inv_data["user"]["invited_by"] == str(admin.id)
    raw_token_1 = inv_data["invite_token"]
    assert raw_token_1 in inv_data["invite_url"]

    # Verify only the SHA-256 hash is stored in DB, never the raw token
    token_row_1 = db.execute(
        select(UserActionToken).where(
            UserActionToken.user_id == invited_user_id,
            UserActionToken.token_type == ActionTokenType.INVITE.value,
        )
    ).scalar_one()
    assert token_row_1.token_hash == hash_action_token(raw_token_1)
    assert token_row_1.token_hash != raw_token_1

    # 3. Resend invite revokes token 1 and issues token 2
    resend_resp = client.post(
        f"/api/v1/admin/users/{invited_user_id}/resend-invite",
        headers=admin_headers,
    )
    assert resend_resp.status_code == 200, resend_resp.text
    raw_token_2 = resend_resp.json()["data"]["invite_token"]
    assert raw_token_2 != raw_token_1

    # Old token 1 is now rejected as revoked
    revoked_attempt = client.post(
        "/api/v1/auth/accept-invite",
        json={"token": raw_token_1, "password": "ValidAcceptPassword123!"},
    )
    assert revoked_attempt.status_code == 400
    assert revoked_attempt.json()["error"]["code"] == "invite_token_revoked"

    # 4. Accept invite with token 2
    accept_resp = client.post(
        "/api/v1/auth/accept-invite",
        json={
            "token": raw_token_2,
            "password": "AcceptedManagerPassword123!",
            "full_name": "Accepted Manager Name",
        },
    )
    assert accept_resp.status_code == 200, accept_resp.text
    accepted_body = accept_resp.json()["data"]
    assert accepted_body["user"]["status"] == "active"
    assert accepted_body["user"]["is_active"] is True
    assert accepted_body["user"]["full_name"] == "Accepted Manager Name"
    assert accepted_body["user"]["last_login_at"] is not None

    # 5. Reusing token 2 is rejected (single-use)
    reuse_attempt = client.post(
        "/api/v1/auth/accept-invite",
        json={"token": raw_token_2, "password": "AnotherValidPassword123!"},
    )
    assert reuse_attempt.status_code == 400
    assert reuse_attempt.json()["error"]["code"] == "invite_token_used"

    # 6. Test expired and revoked invite flows on a second invitee
    invite_email_2 = f"invited-exp-{uuid.uuid4().hex[:8]}@example.com"
    inv2_resp = client.post(
        "/api/v1/admin/users/invite",
        headers=admin_headers,
        json={"email": invite_email_2, "role": "ACCOUNTS_AUDIT"},
    )
    assert inv2_resp.status_code == 201
    inv2_data = inv2_resp.json()["data"]
    inv2_user_id = uuid.UUID(inv2_data["user"]["id"])
    _created_user_ids.append(inv2_user_id)
    raw_exp_token = inv2_data["invite_token"]

    # Force expiry in DB
    exp_row = db.execute(
        select(UserActionToken).where(UserActionToken.token_hash == hash_action_token(raw_exp_token))
    ).scalar_one()
    exp_row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()

    exp_attempt = client.post(
        "/api/v1/auth/accept-invite",
        json={"token": raw_exp_token, "password": "ValidPassword12345!"},
    )
    assert exp_attempt.status_code == 400
    assert exp_attempt.json()["error"]["code"] == "invite_token_expired"

    # Resend then explicitly revoke
    resend2 = client.post(
        f"/api/v1/admin/users/{inv2_user_id}/resend-invite",
        headers=admin_headers,
    )
    tok_to_revoke = resend2.json()["data"]["invite_token"]

    revoke_resp = client.post(
        f"/api/v1/admin/users/{inv2_user_id}/revoke-invite",
        headers=admin_headers,
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["data"]["status"] == "deactivated"

    after_revoke = client.post(
        "/api/v1/auth/accept-invite",
        json={"token": tok_to_revoke, "password": "ValidPassword12345!"},
    )
    assert after_revoke.status_code == 400
    assert after_revoke.json()["error"]["code"] == "invite_token_revoked"


def test_immediate_session_revocation_on_deactivate_role_change_and_password_reset(
    client: TestClient,
    db: Session,
) -> None:
    admin, admin_pwd = _create_test_user(db, RoleName.SYSTEM_ADMIN)
    admin_headers = _login(client, admin.email, admin_pwd)

    exec_user, exec_pwd = _create_test_user(db, RoleName.FINANCE_EXECUTIVE)
    exec_headers = _login(client, exec_user.email, exec_pwd)

    # Token works before role change
    assert client.get("/api/v1/documents", headers=exec_headers).status_code == 200

    # 1. Role change bumps token_version -> old JWT is immediately rejected (401)
    role_resp = client.patch(
        f"/api/v1/admin/users/{exec_user.id}/role",
        headers=admin_headers,
        json={"role": "FINANCE_MANAGER"},
    )
    assert role_resp.status_code == 200
    assert client.get("/api/v1/documents", headers=exec_headers).status_code == 401

    # Re-login gets new token with updated role
    exec_headers_2 = _login(client, exec_user.email, exec_pwd)
    assert client.get("/api/v1/documents", headers=exec_headers_2).status_code == 200

    # 2. Deactivate user -> old JWT is immediately rejected (401) and login blocked
    deact_resp = client.post(
        f"/api/v1/admin/users/{exec_user.id}/deactivate",
        headers=admin_headers,
    )
    assert deact_resp.status_code == 200
    assert deact_resp.json()["data"]["status"] == "deactivated"
    assert client.get("/api/v1/documents", headers=exec_headers_2).status_code == 401

    # 3. Reactivate user -> can log in again
    react_resp = client.post(
        f"/api/v1/admin/users/{exec_user.id}/reactivate",
        headers=admin_headers,
    )
    assert react_resp.status_code == 200
    assert react_resp.json()["data"]["status"] == "active"
    exec_headers_3 = _login(client, exec_user.email, exec_pwd)
    assert client.get("/api/v1/documents", headers=exec_headers_3).status_code == 200

    # 4. Admin-initiated password reset -> single-use token resets password and invalidates old JWT
    reset_req = client.post(
        f"/api/v1/admin/users/{exec_user.id}/reset-password",
        headers=admin_headers,
    )
    assert reset_req.status_code == 200
    reset_token = reset_req.json()["data"]["reset_token"]

    complete_resp = client.post(
        "/api/v1/auth/reset-password",
        json={"token": reset_token, "password": "ResetCompletePassword789!"},
    )
    assert complete_resp.status_code == 200

    # Old JWT invalidated
    assert client.get("/api/v1/documents", headers=exec_headers_3).status_code == 401
    # Reusing reset token fails
    assert (
        client.post(
            "/api/v1/auth/reset-password",
            json={"token": reset_token, "password": "AnotherResetPassword789!"},
        ).status_code
        == 400
    )

    # Verify audit log events written for target user
    logs = (
        db.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == "USER", AuditLog.entity_id == exec_user.id)
            .order_by(AuditLog.created_at.asc())
        )
        .scalars()
        .all()
    )
    logged_actions = {log.action for log in logs}
    assert "user.role_changed" in logged_actions
    assert "user.deactivated" in logged_actions
    assert "user.reactivated" in logged_actions
    assert "password.reset_requested" in logged_actions
    assert "password.changed" in logged_actions

