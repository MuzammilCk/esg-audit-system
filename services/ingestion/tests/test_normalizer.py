import base64
from io import BytesIO
from uuid import uuid4

import fitz  # PyMuPDF
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from services.ingestion.normalizer import create_app


def _make_sample_pdf_with_table_and_image() -> bytes:
    # Create a simple 2-page PDF:
    # - Page 1: a grid table with headers
    # - Page 2: an embedded PNG image
    doc = fitz.open()

    # Page 1 with a table
    page1 = doc.new_page()
    page1.insert_text((50, 30), "ESG Report", fontsize=14)

    # Table coordinates
    x_left, x_mid, x_right = 50, 250, 500
    y_top, y1, y2, y_bottom = 60, 90, 120, 150

    shape = page1.new_shape()

    # Horizontal lines
    shape.draw_line((x_left, y_top), (x_right, y_top))
    shape.draw_line((x_left, y1), (x_right, y1))
    shape.draw_line((x_left, y2), (x_right, y2))
    shape.draw_line((x_left, y_bottom), (x_right, y_bottom))

    # Vertical lines
    shape.draw_line((x_left, y_top), (x_left, y_bottom))
    shape.draw_line((x_mid, y_top), (x_mid, y_bottom))
    shape.draw_line((x_right, y_top), (x_right, y_bottom))

    shape.finish(width=1)
    shape.commit()

    # Header row
    page1.insert_text((x_left + 5, y_top + 20), "Metric", fontsize=10)
    page1.insert_text((x_mid + 5, y_top + 20), "Value", fontsize=10)

    # Row 1
    page1.insert_text((x_left + 5, y1 + 20), "CO2", fontsize=10)
    page1.insert_text((x_mid + 5, y1 + 20), "123", fontsize=10)

    # Row 2
    page1.insert_text((x_left + 5, y2 + 20), "Water", fontsize=10)
    page1.insert_text((x_mid + 5, y2 + 20), "456", fontsize=10)

    # Page 2 with an image
    page2 = doc.new_page()
    page2.insert_text((50, 30), "Image Page", fontsize=14)

    img = Image.new("RGB", (64, 64), color=(255, 0, 0))
    buf = BytesIO()
    img.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    rect = fitz.Rect(50, 60, 114, 124)
    page2.insert_image(rect, stream=img_bytes)

    pdf_bytes = doc.tobytes()
    doc.close()

    return pdf_bytes


def test_normalize_pdf_extracts_table_headers_and_images(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure DB is disabled for this test.
    monkeypatch.delenv("NORMALIZER_POSTGRES_DSN", raising=False)

    pdf_bytes = _make_sample_pdf_with_table_and_image()

    doc_id = uuid4()
    payload = {
        "document_id": str(doc_id),
        "raw_bytes": base64.b64encode(pdf_bytes).decode("ascii"),
        "metadata": {"original_name": "sample_esg_report.pdf"},
        "mime_type": "application/pdf",
        "source_url": "unit-test://sample_esg_report.pdf",
    }

    app = create_app()
    client = TestClient(app)

    resp = client.post("/normalize", json=payload)
    assert resp.status_code == 200, resp.text

    out = resp.json()

    assert out["document_id"] == str(doc_id)
    assert out["structure"]["pages"] == 2

    # Table headers
    assert out["tables"], "Expected at least one extracted table"
    first_table = next((t for t in out["tables"] if t["page"] == 1), out["tables"][0])
    assert first_table["data"], "Expected table data"

    header = [c.strip() for c in first_table["data"][0]]
    assert "Metric" in header
    assert "Value" in header

    # Images retained with page references
    assert out["images"], "Expected at least one extracted image"
    assert any(img["page"] == 2 and img["base64"] for img in out["images"])

    # Text extracted
    assert "ESG Report" in out["text_content"]
