from __future__ import annotations

import asyncio
import base64
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse
from uuid import uuid4

import aiohttp
import boto3
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError
from fastapi import FastAPI, HTTPException
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .models import IngestRequest, IngestedDocument


class RetryableFetchError(RuntimeError):
    """An error that should be retried with exponential backoff."""


_RETRY_MAX_ATTEMPTS = int(os.getenv("FETCHER_RETRY_MAX_ATTEMPTS", "5"))
_RETRY_WAIT_MULTIPLIER = float(os.getenv("FETCHER_RETRY_WAIT_MULTIPLIER", "0.5"))
_RETRY_WAIT_MIN_SECONDS = float(os.getenv("FETCHER_RETRY_WAIT_MIN_SECONDS", "0.5"))
_RETRY_WAIT_MAX_SECONDS = float(os.getenv("FETCHER_RETRY_WAIT_MAX_SECONDS", "8"))

_HTTP_TIMEOUT_SECONDS = float(os.getenv("FETCHER_HTTP_TIMEOUT_SECONDS", "30"))

_ALLOWED_LOCAL_ROOT = os.getenv("FETCHER_ALLOWED_LOCAL_ROOT")


@dataclass(frozen=True)
class _FetchedBytes:
    content: bytes
    source_url: str
    original_name: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _encode_b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _detect_mime_type(raw: bytes, *, filename: Optional[str] = None) -> str:
    # Primary: python-magic (libmagic)
    try:
        import magic  # type: ignore

        try:
            # python-magic exposes from_buffer in most environments
            return str(magic.from_buffer(raw, mime=True))
        except Exception:
            m = magic.Magic(mime=True)
            return str(m.from_buffer(raw))
    except Exception:
        # Fallback: best-effort guess by filename
        import mimetypes

        if filename:
            guessed, _ = mimetypes.guess_type(filename)
            if guessed:
                return guessed
        return "application/octet-stream"


def _merge_metadata(*, extracted: Dict[str, Any], provided: Dict[str, Any]) -> Dict[str, Any]:
    # Ensure extracted keys always exist and take precedence.
    merged: Dict[str, Any] = dict(provided or {})
    merged.update(extracted)
    return merged


def _validate_http_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_url",
                "message": "Expected an http(s) URL.",
                "url": url,
            },
        )
    return url


def _extract_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name
    return name or "download"


def _parse_s3_path(path: str) -> Tuple[str, str]:
    # Accept s3://bucket/key or https://bucket.s3.amazonaws.com/key
    if path.startswith("s3://"):
        no_scheme = path[len("s3://") :]
        parts = no_scheme.split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "invalid_s3_path",
                    "message": "Expected s3://bucket/key",
                    "path": path,
                },
            )
        return parts[0], parts[1]

    parsed = urlparse(path)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        host = parsed.netloc
        suffix = ".s3.amazonaws.com"
        if host.endswith(suffix):
            bucket = host[: -len(suffix)]
            key = parsed.path.lstrip("/")
            if bucket and key:
                return bucket, key

    raise HTTPException(
        status_code=422,
        detail={
            "error": "invalid_s3_path",
            "message": "Expected s3://bucket/key or https://bucket.s3.amazonaws.com/key",
            "path": path,
        },
    )


def _validate_local_path(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    else:
        p = p.resolve()

    if _ALLOWED_LOCAL_ROOT:
        root = Path(_ALLOWED_LOCAL_ROOT).expanduser().resolve()
        if p != root and root not in p.parents:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "local_path_forbidden",
                    "message": "Path is outside FETCHER_ALLOWED_LOCAL_ROOT",
                    "path": str(p),
                    "allowed_root": str(root),
                },
            )

    if not p.exists() or not p.is_file():
        raise HTTPException(
            status_code=404,
            detail={
                "error": "file_not_found",
                "message": "Local file does not exist.",
                "path": str(p),
            },
        )

    return p


@retry(
    reraise=True,
    stop=stop_after_attempt(_RETRY_MAX_ATTEMPTS),
    wait=wait_exponential(
        multiplier=_RETRY_WAIT_MULTIPLIER,
        min=_RETRY_WAIT_MIN_SECONDS,
        max=_RETRY_WAIT_MAX_SECONDS,
    ),
    retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError, RetryableFetchError)),
)
async def _http_get_bytes(session: aiohttp.ClientSession, url: str) -> bytes:
    timeout = aiohttp.ClientTimeout(total=_HTTP_TIMEOUT_SECONDS)
    async with session.get(url, timeout=timeout) as resp:
        # Retry on common transient statuses.
        if resp.status in {408, 429, 500, 502, 503, 504}:
            raise RetryableFetchError(f"Upstream returned retryable status {resp.status}")
        if 400 <= resp.status <= 499:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "http_fetch_failed",
                    "message": "Upstream returned a client error.",
                    "url": url,
                    "upstream_status": resp.status,
                },
            )
        if resp.status >= 500:
            raise RetryableFetchError(f"Upstream returned status {resp.status}")
        return await resp.read()


def _s3_client(*, unsigned: bool) -> Any:
    if unsigned:
        return boto3.client("s3", config=Config(signature_version=UNSIGNED))
    return boto3.client("s3")


def _s3_get_object_bytes_sync(*, bucket: str, key: str, unsigned: bool) -> bytes:
    s3 = _s3_client(unsigned=unsigned)
    obj = s3.get_object(Bucket=bucket, Key=key)
    body = obj["Body"]
    return body.read()


_RETRYABLE_S3_ERROR_CODES = {
    "SlowDown",
    "RequestTimeout",
    "Throttling",
    "ThrottlingException",
    "InternalError",
    "ServiceUnavailable",
}


@retry(
    reraise=True,
    stop=stop_after_attempt(_RETRY_MAX_ATTEMPTS),
    wait=wait_exponential(
        multiplier=_RETRY_WAIT_MULTIPLIER,
        min=_RETRY_WAIT_MIN_SECONDS,
        max=_RETRY_WAIT_MAX_SECONDS,
    ),
    retry=retry_if_exception_type((EndpointConnectionError, RetryableFetchError)),
)
async def _s3_get_bytes(bucket: str, key: str, *, unsigned: bool) -> bytes:
    try:
        return await asyncio.to_thread(
            _s3_get_object_bytes_sync, bucket=bucket, key=key, unsigned=unsigned
        )
    except ClientError as e:
        code = str(e.response.get("Error", {}).get("Code", ""))
        if code in _RETRYABLE_S3_ERROR_CODES:
            raise RetryableFetchError(f"Retryable S3 error: {code}") from e
        raise


def _extract_gdrive_file_id(path: str) -> str:
    # Accept file IDs directly or common share URL formats.
    if "/d/" in path:
        # e.g. https://drive.google.com/file/d/<FILE_ID>/view
        maybe = path.split("/d/", 1)[1]
        return maybe.split("/", 1)[0]
    if "id=" in path:
        # e.g. https://drive.google.com/open?id=<FILE_ID>
        maybe = path.split("id=", 1)[1]
        return maybe.split("&", 1)[0]
    return path.strip()


@retry(
    reraise=True,
    stop=stop_after_attempt(_RETRY_MAX_ATTEMPTS),
    wait=wait_exponential(
        multiplier=_RETRY_WAIT_MULTIPLIER,
        min=_RETRY_WAIT_MIN_SECONDS,
        max=_RETRY_WAIT_MAX_SECONDS,
    ),
    retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError, RetryableFetchError)),
)
async def _gdrive_download_bytes(session: aiohttp.ClientSession, *, file_id: str, token: str) -> bytes:
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    timeout = aiohttp.ClientTimeout(total=_HTTP_TIMEOUT_SECONDS)
    headers = {"Authorization": f"Bearer {token}"}
    async with session.get(url, headers=headers, timeout=timeout) as resp:
        if resp.status in {408, 429, 500, 502, 503, 504}:
            raise RetryableFetchError(f"Google Drive returned retryable status {resp.status}")
        if 400 <= resp.status <= 499:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "gdrive_fetch_failed",
                    "message": "Google Drive returned a client error.",
                    "file_id": file_id,
                    "upstream_status": resp.status,
                },
            )
        if resp.status >= 500:
            raise RetryableFetchError(f"Google Drive returned status {resp.status}")
        return await resp.read()


async def _fetch_bytes(app: FastAPI, req: IngestRequest) -> _FetchedBytes:
    if req.source_type == "local":
        p = _validate_local_path(req.path)
        content = await asyncio.to_thread(p.read_bytes)
        return _FetchedBytes(content=content, source_url=req.path, original_name=p.name)

    if req.source_type == "http":
        url = _validate_http_url(req.path)
        try:
            content = await _http_get_bytes(app.state.http_session, url)
        except (aiohttp.ClientError, asyncio.TimeoutError, RetryableFetchError) as e:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "http_unavailable",
                    "message": str(e),
                    "url": url,
                },
            ) from e
        return _FetchedBytes(content=content, source_url=url, original_name=_extract_name_from_url(url))

    if req.source_type == "s3":
        bucket, key = _parse_s3_path(req.path)
        # Try signed first; fall back to anonymous (unsigned) access if credentials are missing/invalid.
        unsigned = False
        try:
            content = await _s3_get_bytes(bucket, key, unsigned=unsigned)
        except NoCredentialsError:
            unsigned = True
            content = await _s3_get_bytes(bucket, key, unsigned=unsigned)
        except ClientError as e:
            code = str(e.response.get("Error", {}).get("Code", ""))
            if code in {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"}:
                try:
                    content = await _s3_get_bytes(bucket, key, unsigned=True)
                except Exception:
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "error": "s3_access_denied",
                            "message": "S3 access denied.",
                            "bucket": bucket,
                            "key": key,
                        },
                    ) from e
            elif code in {"NoSuchBucket", "NoSuchKey"}:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": "s3_not_found",
                        "message": "S3 object not found.",
                        "bucket": bucket,
                        "key": key,
                    },
                ) from e
            else:
                raise HTTPException(
                    status_code=502,
                    detail={
                        "error": "s3_fetch_failed",
                        "message": "Failed to fetch from S3.",
                        "bucket": bucket,
                        "key": key,
                        "s3_error": code,
                    },
                ) from e
        except (EndpointConnectionError, RetryableFetchError) as e:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "s3_unavailable",
                    "message": str(e),
                    "bucket": bucket,
                    "key": key,
                },
            ) from e

        return _FetchedBytes(content=content, source_url=req.path, original_name=Path(key).name or "object")

    if req.source_type == "gdrive":
        file_id = _extract_gdrive_file_id(req.path)
        token = os.getenv("GDRIVE_ACCESS_TOKEN")
        if not token:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "missing_gdrive_token",
                    "message": "Set GDRIVE_ACCESS_TOKEN to download from Google Drive.",
                },
            )
        try:
            content = await _gdrive_download_bytes(app.state.http_session, file_id=file_id, token=token)
        except (aiohttp.ClientError, asyncio.TimeoutError, RetryableFetchError) as e:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "gdrive_unavailable",
                    "message": str(e),
                    "file_id": file_id,
                },
            ) from e
        return _FetchedBytes(content=content, source_url=req.path, original_name=file_id)

    raise HTTPException(
        status_code=422,
        detail={
            "error": "invalid_source_type",
            "message": "Unsupported source_type.",
            "source_type": req.source_type,
        },
    )


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Shared aiohttp session for async HTTP/GDrive fetching.
    app.state.http_session = aiohttp.ClientSession()
    try:
        yield
    finally:
        await app.state.http_session.close()


def create_app() -> FastAPI:
    app = FastAPI(title="document-fetcher", version="1.0.0", lifespan=_lifespan)

    @app.get("/healthz")
    async def healthz() -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/ingest", response_model=IngestedDocument)
    async def ingest(req: IngestRequest) -> IngestedDocument:
        fetched = await _fetch_bytes(app, req)

        mime_type = _detect_mime_type(fetched.content, filename=fetched.original_name)
        extracted_md = {
            "upload_date": _utc_now_iso(),
            "file_size": len(fetched.content),
            "original_name": fetched.original_name,
        }
        merged_md = _merge_metadata(extracted=extracted_md, provided=req.metadata)

        return IngestedDocument(
            document_id=uuid4(),
            raw_bytes=_encode_b64(fetched.content),
            metadata=merged_md,
            mime_type=mime_type,
            source_url=fetched.source_url,
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
