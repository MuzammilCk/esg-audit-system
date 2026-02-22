import base64
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.ingestion.fetcher import create_app


def test_fetch_local_pdf_base64(tmp_path: Path) -> None:
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj\n"
        b"<< /Type /Catalog >>\n"
        b"endobj\n"
        b"trailer\n"
        b"<<>>\n"
        b"%%EOF\n"
    )
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(pdf_bytes)

    app = create_app()
    client = TestClient(app)

    resp = client.post(
        "/ingest",
        json={"source_type": "local", "path": str(pdf_path), "metadata": {}},
    )

    assert resp.status_code == 200, resp.text
    payload = resp.json()

    decoded = base64.b64decode(payload["raw_bytes"])
    assert decoded == pdf_bytes

    assert payload["metadata"]["file_size"] == len(pdf_bytes)
    assert payload["metadata"]["original_name"] == "sample.pdf"
    assert payload["source_url"] == str(pdf_path)


@pytest.mark.integration
def test_fetch_public_s3_object_metadata() -> None:
    """Integration test against a public S3 object.

    Provide a public bucket + key via env vars:
      PUBLIC_S3_BUCKET, PUBLIC_S3_KEY

    Example path format the service expects:
      s3://<bucket>/<key>
    """

    bucket = os.getenv("PUBLIC_S3_BUCKET")
    key = os.getenv("PUBLIC_S3_KEY")
    if not bucket or not key:
        pytest.skip("Set PUBLIC_S3_BUCKET and PUBLIC_S3_KEY to run S3 integration test.")

    app = create_app()
    client = TestClient(app)

    s3_path = f"s3://{bucket}/{key}"
    resp = client.post(
        "/ingest",
        json={"source_type": "s3", "path": s3_path, "metadata": {}},
    )

    assert resp.status_code == 200, resp.text
    payload = resp.json()

    assert payload["metadata"]["original_name"] == Path(key).name
    assert payload["metadata"]["file_size"] > 0
    assert "upload_date" in payload["metadata"]

    raw = base64.b64decode(payload["raw_bytes"])
    assert len(raw) == payload["metadata"]["file_size"]


def test_invalid_url_returns_4xx() -> None:
    app = create_app()
    client = TestClient(app)

    resp = client.post(
        "/ingest",
        json={"source_type": "http", "path": "not-a-valid-url", "metadata": {}},
    )

    assert 400 <= resp.status_code < 500
