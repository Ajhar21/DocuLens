from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, timezone
from decimal import Decimal
import io
import uuid

from fastapi.testclient import TestClient
import pytest
import sqlalchemy as sa
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.ai.base import l2_normalize_vector, validate_and_normalize_embeddings
from app.ai.fake import FakeEmbeddingProvider
from app.ai.registry import set_embedding_provider_override
from app.core.config import MIGRATION_EMBEDDING_DIM
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models.chunk import DocumentChunk
from app.models.document import Document, DocumentStatus
from app.models.extraction import ExtractedInvoice
from app.models.user import RoleName, User
from app.repositories.user_repo import get_role_by_name
from app.services.storage import storage_service

_search_user_ids: list[uuid.UUID] = []
_search_doc_ids: list[uuid.UUID] = []


class DeterministicSearchEmbeddingProvider(FakeEmbeddingProvider):
    """Embedding provider that yields identical normalized vectors for matching text."""

    def embed_query(self, text: str) -> list[float]:
        # Return identical vector to doc vector so cosine similarity is 1.0
        return self.embed_documents([text])[0]


@pytest.fixture(autouse=True)
def setup_embedding_provider() -> Generator[None, None, None]:
    provider = DeterministicSearchEmbeddingProvider()
    set_embedding_provider_override(provider)
    yield
    set_embedding_provider_override(None)


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def db_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def cleanup_search_records(db_session: Session) -> Generator[None, None, None]:
    yield
    db_session.rollback()
    if _search_doc_ids:
        # Delete chunks, invoices, then documents
        db_session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id.in_(_search_doc_ids))
        )
        db_session.execute(
            delete(ExtractedInvoice).where(
                ExtractedInvoice.document_id.in_(_search_doc_ids)
            )
        )
        db_session.execute(
            delete(Document).where(Document.id.in_(_search_doc_ids))
        )
        db_session.commit()

    if _search_user_ids:
        db_session.execute(
            delete(User).where(User.id.in_(_search_user_ids))
        )
        db_session.commit()


def _seed_user(db: Session, role_name: RoleName) -> tuple[User, str]:
    role_obj = get_role_by_name(db, role_name.value)
    assert role_obj is not None
    uid = uuid.uuid4().hex[:8]
    password = "TestPassword123!"
    user = User(
        email=f"search_{role_name.value.lower()}_{uid}@example.com",
        full_name=f"Search Tester {role_name.value}",
        password_hash=hash_password(password),
        role_id=role_obj.id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _search_user_ids.append(user.id)
    return user, password


def _login_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    resp = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_search_document(
    db: Session,
    user: User,
    *,
    filename: str = "search_test.pdf",
    chunk_content: str = "Industrial gas turbine parts and maintenance invoice",
    invoice_number: str = "INV-SEARCH-001",
    supplier_name: str = "Turbine Dynamics Ltd",
    customer_name: str = "DocuLens Power Inc",
    invoice_date: date = date(2026, 4, 15),
    total: Decimal = Decimal("45000.0000"),
    review_status: str = "pending",
) -> Document:
    doc_id = uuid.uuid4()
    dummy_bytes = b"%PDF-1.4 test invoice content"
    stored = storage_service.save_stream(
        stream=io.BytesIO(dummy_bytes),
        document_id=doc_id,
        ext=".pdf",
        max_bytes=10 * 1024 * 1024,
    )

    doc = Document(
        id=doc_id,
        original_filename=filename,
        stored_path=stored.stored_path,
        content_type="application/pdf",
        file_ext=".pdf",
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        status=DocumentStatus.PARSED.value,
        review_status=review_status,
        uploaded_by=user.id,
    )
    db.add(doc)
    db.flush()

    inv = ExtractedInvoice(
        document_id=doc_id,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        supplier_name=supplier_name,
        customer_name=customer_name,
        subtotal=total - Decimal("500.0000"),
        tax=Decimal("500.0000"),
        total=total,
        currency="USD",
        extraction_metadata={"raw_llm_output": {"invoice_number": invoice_number}},
    )
    db.add(inv)

    provider = DeterministicSearchEmbeddingProvider()
    vec = provider.embed_documents([chunk_content])[0]

    chunk = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc_id,
        page_number=1,
        chunk_index=0,
        content=chunk_content,
        embedding=vec,
        embedding_model="deterministic-search-001",
        created_at=datetime.now(timezone.utc),
    )
    db.add(chunk)
    db.commit()
    db.refresh(doc)
    _search_doc_ids.append(doc.id)
    return doc


def test_search_unauthenticated_returns_401(client: TestClient) -> None:
    resp = client.get("/api/v1/search?q=turbine")
    assert resp.status_code == 401


def test_search_empty_query_returns_422(client: TestClient, db_session: Session) -> None:
    user, pwd = _seed_user(db_session, RoleName.FINANCE_EXECUTIVE)
    headers = _login_headers(client, user.email, pwd)

    resp = client.get("/api/v1/search?q=", headers=headers)
    assert resp.status_code == 422


def test_search_invalid_mode_returns_422(client: TestClient, db_session: Session) -> None:
    user, pwd = _seed_user(db_session, RoleName.FINANCE_EXECUTIVE)
    headers = _login_headers(client, user.email, pwd)

    resp = client.get("/api/v1/search?q=turbine&mode=magical", headers=headers)
    assert resp.status_code == 422


def test_keyword_search_matches_chunk_and_header(client: TestClient, db_session: Session) -> None:
    user, pwd = _seed_user(db_session, RoleName.FINANCE_EXECUTIVE)
    headers = _login_headers(client, user.email, pwd)

    unique_kw = f"turbine_{uuid.uuid4().hex[:6]}"
    unique_inv = f"INV-KW-{uuid.uuid4().hex[:6]}"
    doc = _create_search_document(
        db_session,
        user,
        chunk_content=f"High pressure {unique_kw} rotor replacement parts",
        invoice_number=unique_inv,
        supplier_name="Global Aerospace Turbine Corp",
    )

    # 1. Search by unique chunk keyword
    resp = client.get(f"/api/v1/search?q={unique_kw}&mode=keyword", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["mode"] == "KEYWORD"
    assert data["total_hits"] >= 1
    found = [h for h in data["hits"] if h["document"]["id"] == str(doc.id)]
    assert len(found) == 1
    hit = found[0]
    assert hit["match_type"] == "KEYWORD"
    assert hit["score"] > 0
    assert hit["invoice"]["invoice_number"] == unique_inv
    hit_snippet_clean = hit["snippet"].lower().replace("<mark>", "").replace("</mark>", "")
    assert unique_kw in hit_snippet_clean

    # 2. Search by invoice number
    resp_inv = client.get(f"/api/v1/search?q={unique_inv}&mode=keyword", headers=headers)
    assert resp_inv.status_code == 200, resp_inv.text
    data_inv = resp_inv.json()["data"]
    found_inv = [h for h in data_inv["hits"] if h["document"]["id"] == str(doc.id)]
    assert len(found_inv) == 1


def test_semantic_search_cosine_similarity(client: TestClient, db_session: Session) -> None:
    user, pwd = _seed_user(db_session, RoleName.FINANCE_MANAGER)
    headers = _login_headers(client, user.email, pwd)

    phrase = f"Aerodynamic thermal barrier coatings {uuid.uuid4().hex[:6]}"
    doc = _create_search_document(
        db_session,
        user,
        chunk_content=phrase,
        invoice_number=f"INV-SEM-{uuid.uuid4().hex[:6]}",
    )

    # Semantic search with exact matching phrase
    resp = client.get(f"/api/v1/search?q={phrase}&mode=semantic", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["mode"] == "SEMANTIC"
    found = [h for h in data["hits"] if h["document"]["id"] == str(doc.id)]
    assert len(found) == 1
    hit = found[0]
    assert hit["match_type"] == "SEMANTIC"
    assert hit["score"] >= 0.6


def test_hybrid_search_fusion_both(client: TestClient, db_session: Session) -> None:
    user, pwd = _seed_user(db_session, RoleName.ACCOUNTS_AUDIT)
    headers = _login_headers(client, user.email, pwd)

    phrase = f"Propulsion titanium assemblies {uuid.uuid4().hex[:6]}"
    doc = _create_search_document(
        db_session,
        user,
        chunk_content=phrase,
        invoice_number=f"INV-HYB-{uuid.uuid4().hex[:6]}",
    )

    resp = client.get(f"/api/v1/search?q={phrase}&mode=hybrid", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["mode"] == "HYBRID"
    found = [h for h in data["hits"] if h["document"]["id"] == str(doc.id)]
    assert len(found) == 1
    hit = found[0]
    # Matched both keyword (tsquery) and semantic (vector)
    assert hit["match_type"] == "BOTH"
    assert hit["score"] > 0


def test_search_structured_filters(client: TestClient, db_session: Session) -> None:
    user, pwd = _seed_user(db_session, RoleName.SYSTEM_ADMIN)
    headers = _login_headers(client, user.email, pwd)

    tag = uuid.uuid4().hex[:6]
    target_supplier = f"Specialty Supplier {tag}"
    other_supplier = f"Other Supplier {tag}"

    doc1 = _create_search_document(
        db_session,
        user,
        chunk_content=f"Hydraulic pump maintenance {tag}",
        invoice_number=f"INV-FLT-1-{tag}",
        supplier_name=target_supplier,
        invoice_date=date(2026, 5, 10),
        total=Decimal("12500.0000"),
        review_status="approved",
    )
    doc2 = _create_search_document(
        db_session,
        user,
        chunk_content=f"Hydraulic pump inspection {tag}",
        invoice_number=f"INV-FLT-2-{tag}",
        supplier_name=other_supplier,
        invoice_date=date(2026, 6, 20),
        total=Decimal("3000.0000"),
        review_status="pending",
    )

    # Filter by supplier_name
    resp = client.get(
        f"/api/v1/search?q=hydraulic&supplier_name={target_supplier}",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    hits = resp.json()["data"]["hits"]
    doc_ids = [h["document"]["id"] for h in hits]
    assert str(doc1.id) in doc_ids
    assert str(doc2.id) not in doc_ids

    # Filter by amount_min
    resp = client.get(
        f"/api/v1/search?q=hydraulic&amount_min=10000",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    hits = resp.json()["data"]["hits"]
    doc_ids = [h["document"]["id"] for h in hits]
    assert str(doc1.id) in doc_ids
    assert str(doc2.id) not in doc_ids

    # Filter by date_from and date_to
    resp = client.get(
        f"/api/v1/search?q=hydraulic&date_from=2026-06-01&date_to=2026-06-30",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    hits = resp.json()["data"]["hits"]
    doc_ids = [h["document"]["id"] for h in hits]
    assert str(doc2.id) in doc_ids
    assert str(doc1.id) not in doc_ids

    # Filter by review_status
    resp = client.get(
        f"/api/v1/search?q=hydraulic&review_status=approved",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    hits = resp.json()["data"]["hits"]
    doc_ids = [h["document"]["id"] for h in hits]
    assert str(doc1.id) in doc_ids
    assert str(doc2.id) not in doc_ids


def test_search_single_visibility_rule_enforced(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user1, pwd1 = _seed_user(db_session, RoleName.FINANCE_EXECUTIVE)
    user2, pwd2 = _seed_user(db_session, RoleName.FINANCE_EXECUTIVE)
    headers1 = _login_headers(client, user1.email, pwd1)
    headers2 = _login_headers(client, user2.email, pwd2)

    unique_kw = f"stealth_{uuid.uuid4().hex[:6]}"
    doc = _create_search_document(
        db_session,
        user1,
        chunk_content=f"Secret project {unique_kw} deliverables",
    )

    # Monkeypatch visibility to uploader-only
    monkeypatch.setattr(
        "app.repositories.search_repo.visible_documents_filter",
        lambda user: Document.uploaded_by == user.id,
    )

    # user1 (uploader) can find the document
    resp1 = client.get(f"/api/v1/search?q={unique_kw}", headers=headers1)
    assert resp1.status_code == 200, resp1.text
    assert any(h["document"]["id"] == str(doc.id) for h in resp1.json()["data"]["hits"])

    # user2 cannot find the document
    resp2 = client.get(f"/api/v1/search?q={unique_kw}", headers=headers2)
    assert resp2.status_code == 200, resp2.text
    assert not any(h["document"]["id"] == str(doc.id) for h in resp2.json()["data"]["hits"])
