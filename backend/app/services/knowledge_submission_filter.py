"""Fail-closed content screening for contributed knowledge documents."""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile


@dataclass(frozen=True)
class SubmissionFilterResult:
    accepted: bool
    reason: str | None = None


class KnowledgeSubmissionFilter:
    def __init__(
        self,
        *,
        blocked_keywords: str,
        reject_images: bool,
        scan_max_chars: int,
    ) -> None:
        self._blocked_keywords = [
            item.strip() for item in blocked_keywords.replace("\n", ",").split(",") if item.strip()
        ]
        self._reject_images = reject_images
        self._scan_max_chars = max(1, scan_max_chars)

    def screen(
        self,
        *,
        filename: str,
        payload: bytes,
        title: str | None,
        description: str | None,
    ) -> SubmissionFilterResult:
        suffix = Path(filename).suffix.lower()
        try:
            text, has_images = self._extract(suffix=suffix, payload=payload)
        except (BadZipFile, ElementTree.ParseError, OSError, UnicodeError, ValueError) as exc:
            return SubmissionFilterResult(False, f"自动驳回：文件无法安全解析（{type(exc).__name__}）")
        except Exception:
            return SubmissionFilterResult(False, "自动驳回：文件内容检查失败")

        if self._reject_images and has_images:
            return SubmissionFilterResult(False, "自动驳回：文档包含图片，请移除图片后重新投稿")

        haystack = "\n".join([filename, title or "", description or "", text])[: self._scan_max_chars]
        normalized = haystack.casefold()
        for keyword in self._blocked_keywords:
            if keyword.casefold() in normalized:
                return SubmissionFilterResult(False, f"自动驳回：内容命中违禁关键词“{keyword}”")
        return SubmissionFilterResult(True)

    def _extract(self, *, suffix: str, payload: bytes) -> tuple[str, bool]:
        if suffix in {".md", ".txt"}:
            return payload.decode("utf-8"), False
        if suffix in {".json", ".jsonl"}:
            text = payload.decode("utf-8")
            if suffix == ".json":
                json.loads(text)
            else:
                for line in text.splitlines():
                    if line.strip():
                        json.loads(line)
            return text, False
        if suffix == ".docx":
            return self._extract_docx(payload)
        if suffix == ".pdf":
            return self._extract_pdf(payload)
        if suffix == ".doc":
            raise ValueError("legacy_doc_not_safely_scannable")
        raise ValueError("unsupported_submission_type")

    def _extract_docx(self, payload: bytes) -> tuple[str, bool]:
        with ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
            has_images = any(name.startswith("word/media/") and not name.endswith("/") for name in names)
            document = archive.read("word/document.xml")
        root = ElementTree.fromstring(document)
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        text = "\n".join(
            "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace))
            for paragraph in root.findall(".//w:p", namespace)
        )
        return text, has_images

    def _extract_pdf(self, payload: bytes) -> tuple[str, bool]:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(payload))
        parts: list[str] = []
        has_images = False
        for page in reader.pages:
            parts.append(str(page.extract_text() or ""))
            resources = page.get("/Resources")
            if resources is None:
                continue
            resources = resources.get_object()
            xobjects = resources.get("/XObject")
            if xobjects is None:
                continue
            xobjects = xobjects.get_object()
            for item in xobjects.values():
                obj = item.get_object()
                if obj.get("/Subtype") == "/Image":
                    has_images = True
                    break
        return "\n".join(parts), has_images
