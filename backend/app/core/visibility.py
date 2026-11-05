"""Single document visibility rule (PRD assumption #11).

``visible_documents_filter(user)`` is the ONLY place where document visibility
is decided across the backend. It MUST be applied to:
- Document list & detail
- Document file download
- Document status, extraction, validation, reprocess, and history endpoints
- Review queue, detail, corrections, approve, and reject
- Reconciliation document selection and Excel sheet discovery
- Keyword, semantic, and hybrid search (applied in SQL BEFORE ranking)
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.sql.elements import ColumnElement

from app.models.user import User


def visible_documents_filter(user: User) -> ColumnElement[bool]:
    """Return a SQLAlchemy boolean clause restricting ``Document`` rows visible to ``user``.

    Decision: All active authenticated roles can see all documents in MVP,
    so this returns ``sa.true()``. Tightening to organization or uploader
    scoping later is a single-function change here.
    """
    _ = user
    return sa.true()

