from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User, UserRole


def _create_user(
    db: Session,
    email: str,
    password: str,
    role: UserRole = UserRole.VIEWER,
    is_active: bool = True,
) -> User:
    user = User(
        email=email.lower(),
        full_name="Test User",
        password_hash=hash_password(password),
        role=role.value,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    resp = client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_login_success_and_failure(client: TestClient, db: Session) -> None:
    _create_user(db, "reviewer@example.com", "CorrectPass123!", role=UserRole.REVIEWER)

    ok_resp = client.post(
        "/api/auth/login",
        data={"username": "REVIEWER@example.com", "password": "CorrectPass123!"},
    )
    assert ok_resp.status_code == 200
    body = ok_resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"

    me_resp = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "reviewer@example.com"

    bad_resp = client.post(
        "/api/auth/login",
        data={"username": "reviewer@example.com", "password": "WrongPassword"},
    )
    assert bad_resp.status_code == 401


def test_inactive_user_rejected(client: TestClient, db: Session) -> None:
    user = _create_user(
        db,
        "inactive@example.com",
        "Pass123456!",
        role=UserRole.REVIEWER,
        is_active=True,
    )
    headers = _login_headers(client, "inactive@example.com", "Pass123456!")

    user.is_active = False
    db.commit()

    login_resp = client.post(
        "/api/auth/login",
        data={"username": "inactive@example.com", "password": "Pass123456!"},
    )
    assert login_resp.status_code == 401

    me_resp = client.get("/api/auth/me", headers=headers)
    assert me_resp.status_code == 401


def test_viewer_gets_403_on_upload_and_users(client: TestClient, db: Session) -> None:
    _create_user(db, "viewer@example.com", "ViewerPass123!", role=UserRole.VIEWER)
    headers = _login_headers(client, "viewer@example.com", "ViewerPass123!")

    users_resp = client.get("/api/users", headers=headers)
    assert users_resp.status_code == 403

    upload_resp = client.post(
        "/api/documents",
        headers=headers,
        files=[("files", ("sample.csv", b"col1,col2\n1,2\n", "text/csv"))],
    )
    assert upload_resp.status_code == 403

    docs_resp = client.get("/api/documents", headers=headers)
    assert docs_resp.status_code == 200


def test_admin_user_management(client: TestClient, db: Session) -> None:
    _create_user(db, "admin@example.com", "AdminPass123!", role=UserRole.ADMIN)
    headers = _login_headers(client, "admin@example.com", "AdminPass123!")

    create_resp = client.post(
        "/api/users",
        headers=headers,
        json={
            "email": "NewUser@Example.com",
            "full_name": "New Reviewer",
            "password": "ReviewerPass123!",
            "role": "reviewer",
            "is_active": True,
        },
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["email"] == "newuser@example.com"
    assert created["role"] == "reviewer"

    patch_resp = client.patch(
        f"/api/users/{created['id']}",
        headers=headers,
        json={"role": "viewer", "full_name": "Updated Name", "is_active": False},
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["role"] == "viewer"
    assert patched["full_name"] == "Updated Name"
    assert patched["is_active"] is False

    list_resp = client.get("/api/users", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 2


def test_unauthenticated_and_malformed_tokens_rejected(client: TestClient) -> None:
    # 1. No Authorization header
    resp_no_token = client.get("/api/documents")
    assert resp_no_token.status_code == 401
    assert "Not authenticated" in resp_no_token.json().get("detail", "")

    resp_upload_no_token = client.post(
        "/api/documents",
        files=[("files", ("test.csv", b"a,b\n1,2\n", "text/csv"))],
    )
    assert resp_upload_no_token.status_code == 401

    resp_me_no_token = client.get("/api/auth/me")
    assert resp_me_no_token.status_code == 401

    # 2. Malformed Bearer token
    resp_bad_token = client.get(
        "/api/documents",
        headers={"Authorization": "Bearer invalid.jwt.signature"},
    )
    assert resp_bad_token.status_code == 401
    assert "Could not validate credentials" in resp_bad_token.json().get("detail", "")

    # 3. Wrong auth scheme
    resp_basic = client.get(
        "/api/documents",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert resp_basic.status_code == 401

