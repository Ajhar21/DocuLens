from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User, UserRole


def _seed_user(
    db: Session,
    email: str,
    password: str,
    role: UserRole = UserRole.ADMIN,
) -> User:
    user = User(
        email=email.lower(),
        full_name="Seeded User",
        password_hash=hash_password(password),
        role=role.value,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    resp = client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_users_crud_and_duplicate_conflict(client: TestClient, db: Session) -> None:
    uid = uuid.uuid4().hex[:8]
    admin_email = f"test-admin-{uid}@example.com"
    alice_email = f"test-alice-{uid}@example.com"
    admin = _seed_user(db, admin_email, "AdminPass123!", role=UserRole.ADMIN)
    alice_id: str | None = None

    try:
        headers = _auth_headers(client, admin_email, "AdminPass123!")

        create_resp = client.post(
            "/api/users",
            headers=headers,
            json={
                "email": f"Test-Alice-{uid}@Example.com",
                "full_name": "Alice Reviewer",
                "password": "AlicePassword123!",
                "role": "reviewer",
                "is_active": True,
            },
        )
        assert create_resp.status_code == 201, create_resp.text
        alice = create_resp.json()["data"]
        alice_id = alice["id"]
        assert alice["email"] == alice_email.lower()
        assert alice["role"] == "reviewer"
        assert alice["is_active"] is True

        dup_resp = client.post(
            "/api/users",
            headers=headers,
            json={
                "email": alice_email,
                "full_name": "Duplicate Alice",
                "password": "AlicePassword123!",
                "role": "viewer",
                "is_active": True,
            },
        )
        assert dup_resp.status_code == 409
        assert dup_resp.json()["error"]["code"] == "conflict"

        patch_resp = client.patch(
            f"/api/users/{alice['id']}",
            headers=headers,
            json={"full_name": "Alice Updated", "role": "viewer", "is_active": False},
        )
        assert patch_resp.status_code == 200
        updated = patch_resp.json()["data"]
        assert updated["full_name"] == "Alice Updated"
        assert updated["role"] == "viewer"
        assert updated["is_active"] is False

        missing_resp = client.patch(
            f"/api/users/{uuid.uuid4()}",
            headers=headers,
            json={"full_name": "Ghost"},
        )
        assert missing_resp.status_code == 404

        list_resp = client.get("/api/users", headers=headers)
        assert list_resp.status_code == 200
        emails = [u["email"] for u in list_resp.json()["data"]]
        assert admin_email.lower() in emails
        assert alice_email.lower() in emails
    finally:
        if alice_id:
            db.execute(delete(User).where(User.id == uuid.UUID(alice_id)))
        db.delete(admin)
        db.commit()


def test_reviewer_cannot_manage_users(client: TestClient, db: Session) -> None:
    uid = uuid.uuid4().hex[:8]
    rev_email = f"test-rev-{uid}@example.com"
    rev = _seed_user(db, rev_email, "RevPass123!", role=UserRole.REVIEWER)

    try:
        headers = _auth_headers(client, rev_email, "RevPass123!")
        resp = client.get("/api/users", headers=headers)
        assert resp.status_code == 403
    finally:
        db.delete(rev)
        db.commit()
