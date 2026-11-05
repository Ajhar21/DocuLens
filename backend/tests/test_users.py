from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import RoleName, User
from app.repositories.user_repo import get_role_by_name


def _seed_user(
    db: Session,
    email: str,
    password: str,
    role: RoleName = RoleName.SYSTEM_ADMIN,
) -> User:
    role_obj = get_role_by_name(db, role.value)
    user = User(
        email=email.lower(),
        full_name="Seeded User",
        password_hash=hash_password(password),
        role_id=role_obj.id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_users_crud_and_duplicate_conflict(client: TestClient, db: Session) -> None:
    uid = uuid.uuid4().hex[:8]
    admin_email = f"test-admin-{uid}@example.com"
    alice_email = f"test-alice-{uid}@example.com"
    admin = _seed_user(db, admin_email, "AdminPass123!", role=RoleName.SYSTEM_ADMIN)
    alice_id: str | None = None

    try:
        headers = _auth_headers(client, admin_email, "AdminPass123!")

        create_resp = client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "email": f"Test-Alice-{uid}@Example.com",
                "full_name": "Alice Executive",
                "password": "AlicePassword123!",
                "role": "FINANCE_EXECUTIVE",
                "is_active": True,
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        alice = create_resp.json()["data"]
        alice_id = alice["id"]
        assert alice["email"] == alice_email.lower()
        assert alice["role"] == "FINANCE_EXECUTIVE"
        assert alice["is_active"] is True

        get_resp = client.get(f"/api/v1/users/{alice_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["email"] == alice_email.lower()

        dup_resp = client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "email": alice_email,
                "full_name": "Duplicate Alice",
                "password": "AlicePassword123!",
                "role": "ACCOUNTS_AUDIT",
                "is_active": True,
            },
        )
        assert dup_resp.status_code == 409
        assert dup_resp.json()["error"]["code"] == "conflict"

        role_resp = client.patch(
            f"/api/v1/users/{alice['id']}/role",
            headers=headers,
            json={"role": "FINANCE_MANAGER"},
        )
        assert role_resp.status_code == 200
        assert role_resp.json()["data"]["role"] == "FINANCE_MANAGER"

        status_resp = client.patch(
            f"/api/v1/users/{alice['id']}/status",
            headers=headers,
            json={"is_active": False},
        )
        assert status_resp.status_code == 200
        assert status_resp.json()["data"]["is_active"] is False

        patch_resp = client.patch(
            f"/api/v1/users/{alice['id']}",
            headers=headers,
            json={"full_name": "Alice Updated", "role": "ACCOUNTS_AUDIT", "is_active": False},
        )
        assert patch_resp.status_code == 200
        updated = patch_resp.json()["data"]
        assert updated["full_name"] == "Alice Updated"
        assert updated["role"] == "ACCOUNTS_AUDIT"
        assert updated["is_active"] is False

        missing_resp = client.patch(
            f"/api/v1/users/{uuid.uuid4()}",
            headers=headers,
            json={"full_name": "Ghost"},
        )
        assert missing_resp.status_code == 404

        list_resp = client.get("/api/v1/users", headers=headers)
        assert list_resp.status_code == 200
        emails = [u["email"] for u in list_resp.json()["data"]]
        assert admin_email.lower() in emails
        assert alice_email.lower() in emails
    finally:
        if alice_id:
            db.execute(delete(User).where(User.id == uuid.UUID(alice_id)))
        db.delete(admin)
        db.commit()


def test_non_admin_roles_cannot_manage_users(client: TestClient, db: Session) -> None:
    for role in (
        RoleName.FINANCE_EXECUTIVE,
        RoleName.FINANCE_MANAGER,
        RoleName.ACCOUNTS_AUDIT,
    ):
        uid = uuid.uuid4().hex[:8]
        email = f"test-{role.value.lower()}-{uid}@example.com"
        user = _seed_user(db, email, "RolePass123!", role=role)
        try:
            headers = _auth_headers(client, email, "RolePass123!")
            resp = client.get("/api/v1/users", headers=headers)
            assert resp.status_code == 403
        finally:
            db.delete(user)
            db.commit()
