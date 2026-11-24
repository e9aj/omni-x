from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from omnix.document_intelligence import DocumentError, DocumentExtractor


def test_extracts_text_and_docx_without_leaving_workspace(tmp_path: Path):
    (tmp_path / "note.txt").write_text("local document", encoding="utf-8")
    result = DocumentExtractor(tmp_path).extract("note.txt")
    assert result["text"] == "local document"
    document_xml = """<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p><w:r><w:t>DOCX text</w:t></w:r></w:p></w:body></w:document>"""
    with ZipFile(tmp_path / "note.docx", "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", document_xml)
    assert DocumentExtractor(tmp_path).extract("note.docx")["text"] == "DOCX text"
    with pytest.raises(DocumentError):
        DocumentExtractor(tmp_path).extract("../outside.pdf")


def test_pdf_extraction_uses_local_pypdf(tmp_path: Path):
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with (tmp_path / "blank.pdf").open("wb") as handle:
        writer.write(handle)
    result = DocumentExtractor(tmp_path).extract("blank.pdf")
    assert result["type"] == "pdf"
    assert result["pages"] == 1


def test_docx_archive_limits_reject_zip_bomb_shape(tmp_path: Path):
    with ZipFile(tmp_path / "large.docx", "w", ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", "x" * 10_000_001)
    with pytest.raises(DocumentError, match="entry exceeds"):
        DocumentExtractor(tmp_path).extract("large.docx")
