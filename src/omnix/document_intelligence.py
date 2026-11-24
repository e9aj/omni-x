"""Contained local document extraction for Brain indexing."""

from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path
from xml.etree import ElementTree


class DocumentError(ValueError):
    pass


class DocumentExtractor:
    def __init__(self, root: Path, *, allow_ocr: bool = False, audit=None):
        self.root = root.expanduser().resolve()
        self.allow_ocr, self.audit = allow_ocr, audit

    def _path(self, path: str) -> Path:
        candidate = (self.root / path).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise DocumentError("document path escapes workspace") from exc
        if not candidate.is_file() or candidate.stat().st_size > 25_000_000:
            raise DocumentError("document is missing or exceeds the 25 MB limit")
        if candidate.suffix.lower() not in {".pdf", ".docx", ".txt", ".md"}:
            raise DocumentError("unsupported document type")
        return candidate

    def extract(self, path: str) -> dict[str, object]:
        candidate = self._path(path)
        suffix = candidate.suffix.lower()
        if suffix in {".txt", ".md"}:
            text = candidate.read_text(encoding="utf-8")
            pages = 1
        elif suffix == ".docx":
            text = self._docx(candidate)
            pages = 1
        else:
            if importlib.util.find_spec("pypdf") is None:
                raise DocumentError("pypdf is not installed")
            from pypdf import PdfReader
            reader = PdfReader(str(candidate))
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
            pages = len(reader.pages)
        if self.audit:
            self.audit("document_extracted", candidate.suffix.lower())
        return {"path": path, "type": suffix[1:], "pages": pages, "text": text[:10_000_000], "characters": len(text)}

    def _docx(self, path: Path) -> str:
        try:
            with zipfile.ZipFile(path) as archive:
                xml = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml)
        except (KeyError, OSError, ElementTree.ParseError) as exc:
            raise DocumentError("DOCX document is invalid") from exc
        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paragraphs = []
        for paragraph in root.iter(namespace + "p"):
            paragraphs.append("".join(node.text or "" for node in paragraph.iter(namespace + "t")))
        return "\n".join(item for item in paragraphs if item)
