"""
Shared test fixtures.

Every test runs in its own temporary directory with timestamping switched off
by default, so the suite never touches the network and never leaves files
behind. Tests that care about timestamps opt in via the ``local_tsa`` fixture.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # the app package
sys.path.insert(0, HERE)  # test helpers such as tsa_helper

from verifier import load_settings  # noqa: E402
from verifier.certs import ensure_demo_cert  # noqa: E402
from verifier.sample import make_sample_pdf, sample_records  # noqa: E402

COMMCHECKER_VARS = [
    "MODE", "P12_PATH", "P12_BASE64", "P12_PASSWORD", "P12_PASSWORD_FILE",
    "P12_CHAIN_PATH", "DEMO_P12_PATH", "DEMO_P12_PASSWORD", "TSA_URL",
    "TSA_USERNAME", "TSA_PASSWORD", "TSA_TIMEOUT", "TSA_REQUIRED",
    "TRUST_ROOTS", "TRUST_SYSTEM_ROOTS", "ALLOW_FETCHING",
    "MANIFEST_PREVIEWS", "MAX_UPLOAD_MB",
]


@pytest.fixture(autouse=True)
def clean_env(tmp_path, monkeypatch):
    """Isolate every test from the developer's own environment."""
    for name in COMMCHECKER_VARS:
        monkeypatch.delenv(f"COMMCHECKER_{name}", raising=False)
    # No network in the test suite.
    monkeypatch.setenv("COMMCHECKER_TSA_URL", "")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def settings(clean_env):
    s = load_settings()
    ensure_demo_cert(s)
    return s


@pytest.fixture
def sample_pdf():
    return make_sample_pdf()


@pytest.fixture
def records():
    return sample_records()


@pytest.fixture
def local_tsa():
    """An offline RFC-3161 timestamp authority. Returns (timestamper, cert)."""
    from tsa_helper import make_local_tsa

    return make_local_tsa()
