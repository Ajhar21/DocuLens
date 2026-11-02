from __future__ import annotations

import argparse
import logging

from app.db.session import SessionLocal
from app.worker.runner import run_worker


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    parser = argparse.ArgumentParser(description="DocuLens background job worker")
    parser.add_argument(
        "--once",
        "--run-once",
        dest="run_once",
        action="store_true",
        help="Process a single available job and exit",
    )
    args = parser.parse_args()
    run_worker(session_factory=SessionLocal, run_once=args.run_once)


if __name__ == "__main__":
    main()
