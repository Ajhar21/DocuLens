from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import RoleName, User
from app.repositories.user_repo import get_role_by_name


def _create_user(
    db: Session,
    email: str,
    password: str,
    role: RoleName = RoleName.ACCOUNTS_AUDIT,
    is_active: bool = True,
) -> User:
    role_obj = get_role_by_name(db, role.value)
    user = User(
        email=email.lower(),
        full_name="Test User",
        password_hash=hash_password(password),
        role_id=role_obj.id,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_login_success_and_failure(client: TestClient, db: Session) -> None:
    uid = uuid.uuid4().hex[:8]
    email = f"test-exec-{uid}@example.com"
    user = _create_user(db, email, "CorrectPass123!", role=RoleName.FINANCE_EXECUTIVE)

    try:
        ok_resp = client.post(
            "/api/v1/auth/login",
            data={"username": email.upper(), "password": "CorrectPass123!"},
        )
        assert ok_resp.status_code == 200
        body = ok_resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        assert body["user"]["role"] == "FINANCE_EXECUTIVE"

        me_resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["data"]["email"] == email.lower()
        assert me_resp.json()["data"]["role"] == "FINANCE_EXECUTIVE"

        bad_resp = client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": "WrongPassword"},
        )
        assert bad_resp.status_code == 401
        assert bad_resp.json()["error"]["code"] == "invalid_credentials"
        assert bad_resp.headers.get("www-authenticate") == "Bearer"
    finally:
        db.delete(user)
        db.commit()


def test_refresh_token_rotation_and_reuse_detection(
    client: TestClient, db: Session
) -> None:
    uid = uuid.uuid4().hex[:8]
    email = f"test-refresh-{uid}@example.com"
    user = _create_user(db, email, "Pass123456!", role=RoleName.FINANCE_MANAGER)

    try:
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "Pass123456!"},
        )
        assert login_resp.status_code == 200, login_resp.text
        first_refresh = login_resp.json()["refresh_token"]

        # 1. Valid refresh rotates token and returns a new pair
        refresh_resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": first_refresh},
        )
        assert refresh_resp.status_code == 200, refresh_resp.text
        refreshed_data = refresh_resp.json()["data"]
        second_refresh = refreshed_data["refresh_token"]
        assert second_refresh != first_refresh

        # 2. Replaying the already-rotated first_refresh triggers reuse detection
        # and revokes the entire token family (including second_refresh)
        replay_resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": first_refresh},
        )
        assert replay_resp.status_code == 401
        assert replay_resp.json()["error"]["code"] == "refresh_token_reused"

        family_revoked_resp = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": second_refresh},
        )
        assert family_revoked_resp.status_code == 401
        assert family_revoked_resp.json()["error"]["code"] == "refresh_token_reused"
    finally:
        db.delete(user)
        db.commit()


def test_inactive_user_rejected(client: TestClient, db: Session) -> None:
    uid = uuid.uuid4().hex[:8]
    email = f"test-inactive-{uid}@example.com"
    user = _create_user(
        db,
        email,
        "Pass123456!",
        role=RoleName.FINANCE_MANAGER,
        is_active=True,
    )

    try:
        headers = _login_headers(client, email, "Pass123456!")

        user.is_active = False
        db.commit()

        login_resp = client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": "Pass123456!"},
        )
        assert login_resp.status_code == 401
        assert login_resp.json()["error"]["code"] == "account_inactive"

        me_resp = client.get("/api/v1/auth/me", headers=headers)
        assert me_resp.status_code == 401
    finally:
        db.delete(user)
        db.commit()


def test_accounts_audit_gets_403_on_upload_and_users(
    client: TestClient, db: Session
) -> None:
    uid = uuid.uuid4().hex[:8]
    email = f"test-audit-{uid}@example.com"
    user = _create_user(db, email, "AuditPass123!", role=RoleName.ACCOUNTS_AUDIT)

    try:
        headers = _login_headers(client, email, "AuditPass123!")

        users_resp = client.get("/api/v1/users", headers=headers)
        assert users_resp.status_code == 403

        upload_resp = client.post(
            "/api/v1/documents",
            headers=headers,
            files=[("files", ("sample.csv", b"col1,col2\n1,2\n", "text/csv"))],
        )
        assert upload_resp.status_code == 403
        assert upload_resp.json()["error"]["code"] == "forbidden"

        docs_resp = client.get("/api/v1/documents", headers=headers)
        assert docs_resp.status_code == 200
    finally:
        db.delete(user)
        db.commit()


def test_admin_user_management(client: TestClient, db: Session) -> None:
    uid = uuid.uuid4().hex[:8]
    admin_email = f"test-admin-{uid}@example.com"
    new_user_email = f"test-newuser-{uid}@example.com"
    admin = _create_user(db, admin_email, "AdminPass123!", role=RoleName.SYSTEM_ADMIN)
    created_id: str | None = None

    try:
        headers = _login_headers(client, admin_email, "AdminPass123!")

        create_resp = client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "email": new_user_email.upper(),
                "full_name": "New Finance Executive",
                "password": "ExecPass123!",
                "role": "FINANCE_EXECUTIVE",
                "is_active": True,
            },
        )
        assert create_resp.status_code == 201
        created = create_resp.json()["data"]
        created_id = created["id"]
        assert created["email"] == new_user_email.lower()
        assert created["role"] == "FINANCE_EXECUTIVE"

        patch_resp = client.patch(
            f"/api/v1/users/{created['id']}",
            headers=headers,
            json={
                "role": "ACCOUNTS_AUDIT",
                "full_name": "Updated Name",
                "is_active": False,
            },
        )
        assert patch_resp.status_code == 200
        patched = patch_resp.json()["data"]
        assert patched["role"] == "ACCOUNTS_AUDIT"
        assert patched["full_name"] == "Updated Name"
        assert patched["is_active"] is False

        list_resp = client.get("/api/v1/users", headers=headers)
        assert list_resp.status_code == 200
        emails = [u["email"] for u in list_resp.json()["data"]]
        assert len(list_resp.json()["data"]) >= 2
        assert admin_email.lower() in emails
        assert new_user_email.lower() in emails
    finally:
        if created_id:
            db.execute(delete(User).where(User.id == uuid.UUID(created_id)))
        db.delete(admin)
        db.commit()


def test_unauthenticated_and_malformed_tokens_rejected(client: TestClient) -> None:
    # 1. No Authorization header
    resp_no_token = client.get("/api/v1/documents")
    assert resp_no_token.status_code == 401
    assert "Not authenticated" in resp_no_token.json()["message"]
    assert resp_no_token.json()["error"]["code"] == "unauthorized"

    resp_upload_no_token = client.post(
        "/api/v1/documents",
        files=[("files", ("test.csv", b"a,b\n1,2\n", "text/csv"))],
    )
    assert resp_upload_no_token.status_code == 401

    resp_me_no_token = client.get("/api/v1/auth/me")
    assert resp_me_no_token.status_code == 401

    # 2. Malformed Bearer token
    resp_bad_token = client.get(
        "/api/v1/documents",
        headers={"Authorization": "Bearer invalid.jwt.signature"},
    )
    assert resp_bad_token.status_code == 401
    assert "Could not validate credentials" in resp_bad_token.json()["message"]

    # 3. Wrong auth scheme
    resp_basic = client.get(
        "/api/v1/documents",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert resp_basic.status_code == 401
