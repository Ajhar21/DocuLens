"""Script to enqueue a single dummy processing job.

Usage::

    python scripts/enqueue_dummy_job.py
    python -m scripts.enqueue_dummy_job
"""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.db.session import get_db_session
from app.modules.jobs import queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("enqueue_dummy_job")


def main() -> None:
    doc_id = uuid.uuid4()
    logger.info("Generated document_id: %s", doc_id)

    with get_db_session() as session:
        job = queue.enqueue(
            session=session,
            job_type="DOCUMENT_PROCESSING",
            document_id=doc_id,
        )

    print("=" * 60)
    print("SUCCESS: Enqueued dummy job")
    print(f"  Job ID:        {job.id}")
    print(f"  Job Type:      {job.job_type}")
    print(f"  Document ID:   {job.document_id}")
    print(f"  Status:        {job.status}")
    print(f"  Attempt Count: {job.attempt_count}")
    print(f"  Run After:     {job.run_after}")
    print(f"  Created At:    {job.created_at}")
    print("=" * 60)


if __name__ == "__main__":
    main()

