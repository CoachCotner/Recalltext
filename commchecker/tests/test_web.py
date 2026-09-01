"""
The web service.

Two things matter here beyond "does it work": the service must store nothing,
and it must not hand an attacker a way to hurt it with a large or malformed
upload.
"""
import importlib
import os

import pytest
from fastapi.testclient import TestClient

from verifier import seal_bytes


@pytest.fixture
def client(settings):
    """
    A fresh app instance per test.

    The service reads its configuration once at import time - which is what we
    want in production - so tests reload the module to pick up their own
    environment.
    """
    import web.app

    importlib.reload(web.app)
    return TestClient(web.app.app)


@pytest.fixture
def sealed(sample_pdf, settings):
    data, _ = seal_bytes(sample_pdf, settings)
    return data


def post_pdf(client, data, name="record.pdf"):
    return client.post(
        "/verify", files={"file": (name, data, "application/pdf")}
    )


class TestPages:
    def test_the_landing_page_loads(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "Verify a record" in response.text

    def test_the_brand_assets_are_served(self, client):
        for asset in ("/app.css", "/app.js", "/CommChecker_logo_transparent.png", "/CommChecker_icon.png"):
            assert client.get(asset).status_code == 200, asset

    def test_the_brand_colours_are_in_the_stylesheet(self, client):
        css = client.get("/app.css").text
        assert "#071B42" in css   # navy
        assert "#C56230" in css   # burnt orange
        assert "#EDEDED" in css   # soft white

    def test_unknown_paths_404(self, client):
        assert client.get("/does-not-exist").status_code == 404


class TestOperationalEndpoints:
    def test_healthz_reports_ok(self, client):
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_config_shows_the_running_mode(self, client):
        assert client.get("/config").json()["mode"] == "demo"

    def test_config_does_not_leak_secrets(self, client):
        body = client.get("/config").text.lower()
        assert "password" not in body
        assert "p12_base64" not in body


class TestVerifying:
    def test_a_clean_record_passes(self, client, sealed):
        response = post_pdf(client, sealed)
        assert response.status_code == 200
        assert response.json()["verdict"] == "PASS"

    def test_a_tampered_record_fails_and_names_the_record(self, client, sealed):
        tampered = sealed.replace(b"tomorrow at 2.", b"tomorrow at 5.")
        body = post_pdf(client, tampered).json()
        assert body["verdict"] == "FAIL"
        assert [c["id"] for c in body["records"]["changed"]] == ["0003"]

    def test_the_response_carries_the_before_and_after_text(self, client, sealed):
        tampered = sealed.replace(b"tomorrow at 2.", b"tomorrow at 5.")
        changed = post_pdf(client, tampered).json()["records"]["changed"][0]
        assert changed["sealed_text"] == "Confirmed for tomorrow at 2."
        assert changed["current_text"] == "Confirmed for tomorrow at 5."

    def test_an_unsealed_pdf_fails(self, client, sample_pdf):
        assert post_pdf(client, sample_pdf).json()["verdict"] == "FAIL"

    def test_a_non_pdf_fails_without_crashing(self, client):
        response = post_pdf(client, b"just some text", name="notes.txt")
        assert response.status_code == 200
        assert response.json()["verdict"] == "FAIL"

    def test_an_empty_upload_is_rejected(self, client):
        assert post_pdf(client, b"").status_code == 400

    def test_the_filename_is_echoed_back(self, client, sealed):
        body = post_pdf(client, sealed, name="412-maple.pdf").json()
        assert body["file"] == "412-maple.pdf"


class TestUploadLimits:
    def test_an_oversized_upload_is_refused(self, client, monkeypatch):
        import web.app

        monkeypatch.setattr(web.app.SETTINGS, "max_upload_mb", 1)
        response = post_pdf(client, b"x" * (2 * 1024 * 1024))
        assert response.status_code == 413
        assert "larger than" in response.json()["message"]


class TestNothingIsStored:
    def test_no_files_are_left_behind_by_a_verification(
        self, client, sealed, tmp_path
    ):
        """
        The privacy promise on the landing page, enforced as a test.

        Anything the service writes while handling an upload would show up as a
        new file in the working directory.
        """
        before = set(os.listdir(tmp_path))
        assert post_pdf(client, sealed).json()["verdict"] == "PASS"
        assert set(os.listdir(tmp_path)) == before

    def test_no_temporary_files_are_created(self, client, sealed, monkeypatch):
        """The prototype wrote every upload to a temp file. This one must not."""
        import tempfile

        created = []
        real_named = tempfile.NamedTemporaryFile

        def spy(*args, **kwargs):
            created.append(args)
            return real_named(*args, **kwargs)

        monkeypatch.setattr(tempfile, "NamedTemporaryFile", spy)
        post_pdf(client, sealed)
        assert created == [], "the upload was written to a temporary file"

    def test_responses_are_not_cacheable(self, client, sealed):
        assert post_pdf(client, sealed).headers["Cache-Control"] == "no-store"


class TestSecurityHeaders:
    def test_a_content_security_policy_is_set(self, client):
        csp = client.get("/").headers["Content-Security-Policy"]
        assert "default-src 'none'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_the_policy_forbids_inline_scripts(self, client):
        """The page loads its script from a file so the policy can stay strict."""
        assert "'unsafe-inline'" not in client.get("/").headers[
            "Content-Security-Policy"
        ].split("style-src")[0]

    def test_clickjacking_and_sniffing_are_blocked(self, client):
        headers = client.get("/").headers
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["X-Content-Type-Options"] == "nosniff"

    def test_the_page_does_not_inline_its_script(self, client):
        """Inline JS would force a weaker policy, so it must stay external."""
        assert "<script src=" in client.get("/").text
