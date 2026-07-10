"""Persistent review queue for user-contributed knowledge documents."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Literal
from uuid import uuid4

SubmissionStatus = Literal["pending", "approved", "rejected", "withdrawn"]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class KnowledgeSubmission:
    id: str
    owner_user_id: str
    owner_email: str | None
    original_filename: str
    stored_filename: str
    suffix: str
    size_bytes: int
    sha256: str
    title: str | None
    description: str | None
    status: SubmissionStatus
    review_note: str | None
    reviewed_by: str | None
    reviewed_at: str | None
    published_relative_path: str | None
    created_at: str
    updated_at: str


class KnowledgeSubmissionStore:
    def __init__(self, *, metadata_path: Path, files_path: Path) -> None:
        self._metadata_path = metadata_path
        self._files_path = files_path
        self._lock = Lock()

    def create(
        self,
        *,
        owner_user_id: str,
        owner_email: str | None,
        filename: str,
        payload: bytes,
        title: str | None,
        description: str | None,
        automated_rejection_note: str | None = None,
    ) -> KnowledgeSubmission:
        submission_id = uuid4().hex
        suffix = Path(filename).suffix.lower()
        stored_filename = f"{submission_id}{suffix}"
        now = _now()
        item = KnowledgeSubmission(
            id=submission_id,
            owner_user_id=owner_user_id,
            owner_email=owner_email,
            original_filename=filename,
            stored_filename=stored_filename,
            suffix=suffix,
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            title=title,
            description=description,
            status="rejected" if automated_rejection_note else "pending",
            review_note=automated_rejection_note,
            reviewed_by="system:content_filter" if automated_rejection_note else None,
            reviewed_at=now if automated_rejection_note else None,
            published_relative_path=None,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            items = self._load()
            if any(row.sha256 == item.sha256 and row.status in {"pending", "approved"} for row in items):
                raise ValueError("knowledge_submission_duplicate")
            if not automated_rejection_note:
                self._files_path.mkdir(parents=True, exist_ok=True)
                (self._files_path / stored_filename).write_bytes(payload)
            items.append(item)
            self._save(items)
        return item

    def list(self, *, owner_user_id: str | None = None) -> list[KnowledgeSubmission]:
        with self._lock:
            items = self._load()
        if owner_user_id is not None:
            items = [item for item in items if item.owner_user_id == owner_user_id]
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def withdraw(self, submission_id: str, *, owner_user_id: str) -> KnowledgeSubmission | None:
        with self._lock:
            items = self._load()
            item = next((row for row in items if row.id == submission_id and row.owner_user_id == owner_user_id), None)
            if item is None:
                return None
            if item.status != "pending":
                raise ValueError("knowledge_submission_not_pending")
            item.status = "withdrawn"
            item.updated_at = _now()
            self._delete_source(item)
            self._save(items)
            return item

    def review(
        self,
        submission_id: str,
        *,
        reviewer_id: str,
        decision: Literal["approved", "rejected"],
        note: str | None,
        published_directory: Path,
    ) -> KnowledgeSubmission | None:
        with self._lock:
            items = self._load()
            item = next((row for row in items if row.id == submission_id), None)
            if item is None:
                return None
            if item.status != "pending":
                raise ValueError("knowledge_submission_not_pending")
            if decision == "approved":
                source = self._files_path / item.stored_filename
                if not source.is_file():
                    raise ValueError("knowledge_submission_file_missing")
                published_directory.mkdir(parents=True, exist_ok=True)
                safe_name = Path(item.original_filename).name
                target = published_directory / safe_name
                if target.exists():
                    target = published_directory / f"{Path(safe_name).stem}-{item.id[:8]}{item.suffix}"
                shutil.copyfile(source, target)
                item.published_relative_path = target.relative_to(published_directory).as_posix()
            item.status = decision
            item.review_note = note
            item.reviewed_by = reviewer_id
            item.reviewed_at = _now()
            item.updated_at = item.reviewed_at
            self._delete_source(item)
            self._save(items)
            return item

    def _delete_source(self, item: KnowledgeSubmission) -> None:
        path = self._files_path / item.stored_filename
        if path.is_file():
            path.unlink()

    def _load(self) -> list[KnowledgeSubmission]:
        if not self._metadata_path.is_file():
            return []
        try:
            raw = json.loads(self._metadata_path.read_text(encoding="utf-8"))
            return [KnowledgeSubmission(**item) for item in raw if isinstance(item, dict)]
        except (OSError, ValueError, TypeError):
            return []

    def _save(self, items: list[KnowledgeSubmission]) -> None:
        self._metadata_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._metadata_path.with_suffix(f"{self._metadata_path.suffix}.tmp")
        temporary.write_text(json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self._metadata_path)
