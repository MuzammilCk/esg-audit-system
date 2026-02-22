from __future__ import annotations

import base64
from collections import defaultdict
from io import BytesIO
from typing import Any, Dict, List, Tuple

from services.ingestion.models import NormalizedImage, NormalizedTable


def _clean_table(table: List[List[Any]]) -> List[List[str]]:
    cleaned: List[List[str]] = []
    for row in table:
        cleaned_row = []
        for cell in row:
            if cell is None:
                cleaned_row.append("")
            else:
                cleaned_row.append(str(cell).strip())
        # Keep row if there's any non-empty cell.
        if any(c != "" for c in cleaned_row):
            cleaned.append(cleaned_row)
    return cleaned


def _unstructured_pdf_text_and_sections(raw_pdf: bytes) -> Tuple[str, List[Dict[str, Any]]]:
    """Best-effort text extraction and page-level structure using unstructured."""

    try:
        from unstructured.partition.pdf import partition_pdf  # type: ignore
    except Exception:
        return "", []

    try:
        elements = partition_pdf(file=BytesIO(raw_pdf))
    except Exception:
        return "", []

    page_text: Dict[int, List[str]] = defaultdict(list)
    all_text_parts: List[str] = []

    for el in elements:
        text = getattr(el, "text", None)
        if not text:
            continue

        all_text_parts.append(str(text))

        md = getattr(el, "metadata", None)
        page_num = getattr(md, "page_number", None)
        if isinstance(page_num, int) and page_num >= 1:
            page_text[page_num].append(str(text))

    text_content = "\n".join(all_text_parts).strip()

    sections: List[Dict[str, Any]] = []
    for page in sorted(page_text.keys()):
        joined = "\n".join(page_text[page]).strip()
        if joined:
            sections.append(
                {
                    "kind": "page",
                    "page": page,
                    "text_preview": joined[:500],
                }
            )

    return text_content, sections


def parse_pdf(raw_pdf: bytes) -> Dict[str, Any]:
    """Parse a PDF into text, tables, images, and structure."""

    # Pages + images + fallback text via PyMuPDF
    import fitz  # PyMuPDF

    doc = fitz.open(stream=raw_pdf, filetype="pdf")
    try:
        pages = int(doc.page_count)

        images: List[NormalizedImage] = []
        for page_index in range(pages):
            page = doc.load_page(page_index)
            for img in page.get_images(full=True):
                xref = img[0]
                extracted = doc.extract_image(xref)
                img_bytes = extracted.get("image", b"")
                if not img_bytes:
                    continue
                images.append(
                    NormalizedImage(
                        page=page_index + 1,
                        base64=base64.b64encode(img_bytes).decode("ascii"),
                        caption="",
                    )
                )

        # Text + structure from unstructured (preferred)
        text_content, sections = _unstructured_pdf_text_and_sections(raw_pdf)

        # Fallback text if unstructured returns nothing
        if not text_content:
            page_texts: List[str] = []
            for page_index in range(pages):
                page = doc.load_page(page_index)
                txt = page.get_text("text")
                if txt:
                    page_texts.append(txt)
            text_content = "\n".join(page_texts).strip()

            if not sections and page_texts:
                for i, txt in enumerate(page_texts, start=1):
                    if txt.strip():
                        sections.append(
                            {
                                "kind": "page",
                                "page": i,
                                "text_preview": txt.strip()[:500],
                            }
                        )
    finally:
        doc.close()

    # Tables via pdfplumber
    import pdfplumber

    tables: List[NormalizedTable] = []
    with pdfplumber.open(BytesIO(raw_pdf)) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            extracted_tables = page.extract_tables(
                table_settings={
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines",
                    "intersection_tolerance": 5,
                }
            )
            for table in extracted_tables or []:
                cleaned = _clean_table(table)
                if cleaned:
                    tables.append(NormalizedTable(page=idx, data=cleaned))

    return {
        "text_content": text_content,
        "tables": tables,
        "images": images,
        "pages": pages,
        "sections": sections,
    }
