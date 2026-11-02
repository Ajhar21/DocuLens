from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import shutil
from typing import BinaryIO
import uuid

from app.core.config import settings


class StorageValidationError(Exception):
    """Raised when an uploaded file fails size or content validation."""


@dataclass(frozen=True)
class StoredFileInfo:
    stored_path: str
    size_bytes: int
    sha256: str


ALLOWED_EXTENSIONS: set[str] = {".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".csv"}

EXTENSION_CONTENT_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
}


def validate_file_header(ext: str, header: bytes) -> None:
    ext_lower = ext.lower()
    if ext_lower not in ALLOWED_EXTENSIONS:
        raise StorageValidationError(f"Unsupported file extension: {ext_lower or '<none>'}")

    if not header:
        raise StorageValidationError("File is empty (0 bytes)")

    if ext_lower == ".pdf":
        if not header.startswith(b"%PDF-"):
            raise StorageValidationError("Invalid PDF signature (missing %PDF- header)")
    elif ext_lower == ".png":
        if not header.startswith(b"\x89PNG\r\n\x1a\n"):
            raise StorageValidationError("Invalid PNG signature")
    elif ext_lower in {".jpg", ".jpeg"}:
        if not header.startswith(b"\xff\xd8\xff"):
            raise StorageValidationError("Invalid JPEG signature")
    elif ext_lower == ".xlsx":
        if not header.startswith(b"PK\x03\x04"):
            raise StorageValidationError("Invalid XLSX signature (missing ZIP header)")
    elif ext_lower == ".csv":
        if b"\x00" in header:
            raise StorageValidationError("Invalid CSV content (contains binary null bytes)")
        if (
            header.startswith(b"%PDF-")
            or header.startswith(b"\x89PNG\r\n\x1a\n")
            or header.startswith(b"\xff\xd8\xff")
            or header.startswith(b"PK\x03\x04")
        ):
            raise StorageValidationError("Invalid CSV content (binary file signature detected)")
        decoded = False
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                text_sample = header.decode(encoding)
                if text_sample.strip():
                    decoded = True
                    break
            except UnicodeDecodeError:
                continue
        if not decoded:
            raise StorageValidationError("CSV file is empty or not decodable as text")


class StorageBackend(ABC):
    @abstractmethod
    def save_stream(
        self,
        stream: BinaryIO,
        document_id: uuid.UUID,
        ext: str,
        max_bytes: int,
    ) -> StoredFileInfo:
        raise NotImplementedError

    @abstractmethod
    def resolve_path(self, stored_path: str) -> Path:
        raise NotImplementedError

    @abstractmethod
    def delete(self, stored_path: str) -> None:
        raise NotImplementedError


class LocalDiskStorage(StorageBackend):
    CHUNK_SIZE = 64 * 1024

    def _base_dir(self) -> Path:
        return Path(settings.STORAGE_DIR).resolve()

    def save_stream(
        self,
        stream: BinaryIO,
        document_id: uuid.UUID,
        ext: str,
        max_bytes: int,
    ) -> StoredFileInfo:
        ext_clean = ext.lower()
        if ext_clean not in ALLOWED_EXTENSIONS:
            raise StorageValidationError(f"Unsupported file extension: {ext_clean or '<none>'}")

        base_dir = self._base_dir()
        rel_path = Path("documents") / str(document_id) / f"original{ext_clean}"
        dest_path = base_dir / rel_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        hasher = hashlib.sha256()
        total_bytes = 0
        first_chunk = b""

        try:
            with open(dest_path, "wb") as out_file:
                while True:
                    chunk = stream.read(self.CHUNK_SIZE)
                    if not chunk:
                        break
                    if not first_chunk:
                        first_chunk = chunk[:4096]
                        validate_file_header(ext_clean, first_chunk)
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise StorageValidationError(
                            f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_MB} MB"
                        )
                    hasher.update(chunk)
                    out_file.write(chunk)

            if total_bytes == 0:
                raise StorageValidationError("File is empty (0 bytes)")

            return StoredFileInfo(
                stored_path=str(rel_path),
                size_bytes=total_bytes,
                sha256=hasher.hexdigest(),
            )
        except Exception:
            self._cleanup_dir(dest_path.parent)
            raise

    def resolve_path(self, stored_path: str) -> Path:
        base_dir = self._base_dir()
        candidate = (base_dir / stored_path).resolve()
        if os.path.commonpath([str(base_dir), str(candidate)]) != str(base_dir):
            raise ValueError("Invalid stored path traversal attempt")
        return candidate

    def delete(self, stored_path: str) -> None:
        try:
            target = self.resolve_path(stored_path)
            if target.exists():
                target.unlink()
            self._cleanup_dir(target.parent)
        except Exception:
            pass

    @staticmethod
    def _cleanup_dir(directory: Path) -> None:
        try:
            if directory.exists():
                shutil.rmtree(directory, ignore_errors=True)
        except Exception:
            pass


storage_service: StorageBackend = LocalDiskStorage()
