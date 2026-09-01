"""
CommChecker / CommLocker Verify - "Computer #2".

The short version of the API:

    from verifier import seal, verify            # work with files (CLI)
    from verifier import seal_bytes, verify_bytes  # work in memory (web)

Configuration is read from environment variables - see CONFIGURATION.md.
"""
from .config import ConfigError, Settings, load_settings, quiet_library_logs
from .certs import ensure_demo_cert, load_signer, make_demo_cert
from .manifest import (
    MANIFEST_FILENAME,
    Record,
    build_manifest,
    compare_records,
    extract_records,
    read_manifest,
)
from .sealing import SealError, seal, seal_bytes
from .verification import verify, verify_bytes

__all__ = [
    "ConfigError",
    "MANIFEST_FILENAME",
    "Record",
    "SealError",
    "Settings",
    "build_manifest",
    "compare_records",
    "ensure_demo_cert",
    "extract_records",
    "load_settings",
    "quiet_library_logs",
    "load_signer",
    "make_demo_cert",
    "read_manifest",
    "seal",
    "seal_bytes",
    "verify",
    "verify_bytes",
]


def sha256_file(path: str) -> str:
    """Kept from the prototype API."""
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
