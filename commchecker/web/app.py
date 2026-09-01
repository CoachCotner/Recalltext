"""
CommChecker web service.

Run locally:
    uvicorn web.app:app --reload

Run in production:
    uvicorn web.app:app --host 0.0.0.0 --port $PORT

Privacy design
--------------
Uploaded documents are held in memory for the length of one request and then
dropped. Nothing is written to disk, nothing is logged beyond the fact that a
request happened, and there is no database. The service cannot leak documents
it never kept.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response

from verifier import ConfigError, load_settings, quiet_library_logs, verify_bytes
from verifier.certs import ensure_demo_cert

quiet_library_logs()

HERE = os.path.dirname(os.path.abspath(__file__))
CHUNK = 64 * 1024

app = FastAPI(
    title="CommChecker",
    description="Independent verification for sealed CommLocker records.",
    docs_url=None,
    redoc_url=None,
)

# Configuration is read once at startup so a misconfigured server fails
# visibly on /healthz rather than silently on every upload.
SETTINGS = load_settings()
CONFIG_PROBLEMS = SETTINGS.validate()

if not SETTINGS.is_production and not CONFIG_PROBLEMS:
    # Local demos should just work; production never auto-creates anything.
    try:
        ensure_demo_cert(SETTINGS)
    except Exception as e:  # pragma: no cover - startup convenience only
        CONFIG_PROBLEMS.append(f"Could not create the demo certificate: {e}")


# ---------------------------------------------------------------------------
# Static assets, read once into memory
# ---------------------------------------------------------------------------
def _read(name: str, binary: bool = False):
    path = os.path.join(HERE, name)
    mode = "rb" if binary else "r"
    kwargs = {} if binary else {"encoding": "utf-8"}
    with open(path, mode, **kwargs) as f:
        return f.read()


ASSETS = {
    "/app.css": ("text/css; charset=utf-8", _read("app.css").encode("utf-8")),
    "/app.js": ("application/javascript; charset=utf-8", _read("app.js").encode("utf-8")),
    "/cc_logo.png": ("image/png", _read("cc_logo.png", binary=True)),
    "/cc_icon.png": ("image/png", _read("cc_icon.png", binary=True)),
}
INDEX_HTML = _read("index.html")

CSP = (
    "default-src 'none'; "
    "script-src 'self'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "frame-ancestors 'none'"
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    # Verification results are about a document the caller just uploaded; no
    # cache, anywhere, ever.
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


@app.get("/healthz")
def healthz():
    """Liveness plus configuration status. Safe to expose - no secrets."""
    ok = not CONFIG_PROBLEMS
    return JSONResponse(
        {
            "status": "ok" if ok else "misconfigured",
            "mode": SETTINGS.mode,
            "problems": CONFIG_PROBLEMS,
        },
        status_code=200 if ok else 503,
    )


@app.get("/config")
def config():
    """
    The running configuration, with every secret redacted.

    This is how you confirm a production deployment is actually using the
    production certificate and a real timestamp authority.
    """
    return JSONResponse(SETTINGS.describe())


@app.post("/verify")
def verify_endpoint(file: UploadFile = File(...)):
    """
    Verify one uploaded PDF.

    Deliberately a sync function: FastAPI runs it in a worker thread, which
    gives pyHanko's internal event loop a thread of its own instead of
    colliding with the server's.
    """
    if CONFIG_PROBLEMS:
        return JSONResponse(
            {
                "verdict": "FAIL",
                "message": "This CommChecker server is not configured "
                "correctly and cannot verify documents.",
                "checks": [],
                "warnings": CONFIG_PROBLEMS,
                "records": {"manifest_present": False},
                "timestamp": {"present": False},
            },
            status_code=503,
        )

    limit = SETTINGS.max_upload_bytes
    buffer = bytearray()
    while True:
        chunk = file.file.read(CHUNK)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > limit:
            # Stop reading immediately - do not buffer a file we will reject.
            return JSONResponse(
                {
                    "verdict": "FAIL",
                    "message": f"That file is larger than the "
                    f"{SETTINGS.max_upload_mb} MB limit.",
                    "checks": [],
                    "warnings": [],
                    "records": {"manifest_present": False},
                    "timestamp": {"present": False},
                },
                status_code=413,
            )

    data = bytes(buffer)
    if not data:
        return JSONResponse(
            {
                "verdict": "FAIL",
                "message": "That file was empty.",
                "checks": [],
                "warnings": [],
                "records": {"manifest_present": False},
                "timestamp": {"present": False},
            },
            status_code=400,
        )

    try:
        report = verify_bytes(data, SETTINGS, filename=file.filename or "upload.pdf")
    except ConfigError as e:
        return JSONResponse(
            {
                "verdict": "FAIL",
                "message": f"Server configuration problem: {e}",
                "checks": [],
                "warnings": [],
                "records": {"manifest_present": False},
                "timestamp": {"present": False},
            },
            status_code=503,
        )
    finally:
        # Drop the bytes as soon as we are done with them.
        del data
        buffer.clear()

    return JSONResponse(report)


# NOTE: this catch-all must stay the LAST route declared. FastAPI matches routes
# in declaration order, so a path-wildcard registered any earlier would swallow
# /healthz, /config and /verify.
@app.get("/{asset:path}", include_in_schema=False)
def static_asset(asset: str):
    entry = ASSETS.get("/" + asset)
    if entry is None:
        return JSONResponse({"error": "not found"}, status_code=404)
    media_type, payload = entry
    return Response(content=payload, media_type=media_type)
