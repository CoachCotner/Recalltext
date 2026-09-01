"""
Regression tests for defects found in security review.

Every test here corresponds to a way the tool once returned a green PASS, or
crashed, on a document it should have refused. The original suite passed
against all of these, which is exactly why they are pinned here now.

The rule these encode: PASS means every question the tool asked came back
clean. A question it could not answer is never a pass.
"""
import io

import pytest

from verifier import ConfigError, load_settings, seal_bytes, verify_bytes
from verifier.certs import make_demo_cert
from verifier.manifest import MANIFEST_FILENAME, ManifestError, read_manifest
from verifier.sample import render_records_pdf, sample_records
from verifier.verification import _decide_verdict


# ---------------------------------------------------------------------------
# 1. A document sealed with somebody else's certificate
# ---------------------------------------------------------------------------
class TestForgedSigningCertificate:
    """
    The scenario: an impostor exports a doctored thread and seals it with their
    own key. Every byte is consistent with its own seal, so integrity and the
    manifest both check out. Only the signer's identity gives it away.
    """

    @pytest.fixture
    def forged(self, settings, tmp_path):
        attacker_p12 = tmp_path / "attacker.p12"
        make_demo_cert(str(attacker_p12), "x")

        records = sample_records()
        records[4].body = "We reject the terms and demand $50,000 in credits."
        doctored = render_records_pdf(records, title="CommLocker Export")

        attacker_settings = load_settings()
        attacker_settings.demo_p12_path = str(attacker_p12)
        attacker_settings.demo_p12_password = "x"
        sealed, _ = seal_bytes(doctored, attacker_settings)
        return sealed

    def test_a_foreign_certificate_does_not_pass_in_demo_mode(
        self, forged, settings
    ):
        """Demo mode self-trusts its own key - and only its own key."""
        report = verify_bytes(forged, settings)
        assert report["verdict"] == "FAIL"

    def test_the_message_says_the_signer_is_wrong(self, forged, settings):
        assert "NOT sealed by a trusted certificate" in verify_bytes(
            forged, settings
        )["message"]

    def test_the_trust_check_is_red_not_grey(self, forged, settings):
        """A grey 'not evaluated' here would let the banner stay green."""
        checks = {c["check"]: c["ok"] for c in verify_bytes(forged, settings)["checks"]}
        assert checks["Sealed by a trusted certificate"] is False

    def test_a_genuine_document_still_passes(self, sample_pdf, settings):
        """The fix must not make the tool reject its own honest output."""
        sealed, _ = seal_bytes(sample_pdf, settings)
        assert verify_bytes(sealed, settings)["verdict"] == "PASS"


# ---------------------------------------------------------------------------
# 2. No trust roots at all
# ---------------------------------------------------------------------------
class TestUnverifiableSigner:
    def test_production_without_trust_roots_is_a_configuration_error(
        self, clean_env, monkeypatch, tmp_path
    ):
        """
        Previously this configuration validated cleanly, reported healthy, and
        passed every document including forged ones.
        """
        cert = tmp_path / "prod.p12"
        make_demo_cert(str(cert), "pw")
        monkeypatch.setenv("COMMCHECKER_MODE", "production")
        monkeypatch.setenv("COMMCHECKER_P12_PATH", str(cert))
        monkeypatch.setenv("COMMCHECKER_P12_PASSWORD", "pw")
        monkeypatch.setenv("COMMCHECKER_TSA_REQUIRED", "0")
        monkeypatch.setenv("COMMCHECKER_TRUST_SYSTEM_ROOTS", "0")

        assert any("trust roots" in p for p in load_settings().validate())

    def test_an_unverifiable_signer_does_not_pass(self, sample_pdf, settings):
        """With nothing to judge against, the answer is not PASS."""
        sealed, _ = seal_bytes(sample_pdf, settings)

        settings.mode = "production"  # stops demo self-trust
        report = verify_bytes(sealed, settings)

        assert report["verdict"] == "FAIL"
        assert "cannot confirm who sealed it" in report["message"]


# ---------------------------------------------------------------------------
# 3. A broken RFC-3161 timestamp
# ---------------------------------------------------------------------------
class TestBrokenTimestamp:
    """
    The timestamp token sits in the part of the signature the seal's byte range
    excludes, so it can be rewritten without disturbing any other check. The
    verdict has to look at it directly.
    """

    class Status:
        intact = True
        valid = True
        trusted = True

    @staticmethod
    def _report(timestamp):
        return {
            "verdict": "FAIL", "message": "", "checks": [], "warnings": [],
            "seal": {"coverage": "ENTIRE_FILE"},
            "timestamp": timestamp,
            "records": {
                "manifest_present": True,
                "all_records_match": True,
                "record_count_found": 6,
            },
        }

    def test_a_broken_timestamp_fails_an_otherwise_perfect_seal(self):
        report = self._report({"present": True, "intact": False, "trusted": False})
        _decide_verdict(report, self.Status(), "configured")
        assert report["verdict"] == "FAIL"
        assert "BROKEN" in report["message"]

    def test_a_good_timestamp_still_passes(self):
        report = self._report({"present": True, "intact": True, "trusted": True})
        _decide_verdict(report, self.Status(), "configured")
        assert report["verdict"] == "PASS"

    def test_an_untrusted_timestamp_is_a_warning_not_a_failure(self):
        """
        Not knowing the authority is a configuration gap, not evidence of
        tampering - it must not be treated as the same thing.
        """
        report = self._report({"present": True, "intact": True, "trusted": False})
        _decide_verdict(report, self.Status(), "configured")
        assert report["verdict"] == "PASS"

    def test_no_timestamp_still_passes(self):
        report = self._report({"present": False})
        _decide_verdict(report, self.Status(), "configured")
        assert report["verdict"] == "PASS"


# ---------------------------------------------------------------------------
# 4. A hostile manifest attachment
# ---------------------------------------------------------------------------
HOSTILE_MANIFESTS = [
    pytest.param(b"[]", id="json-list"),
    pytest.param(b"123", id="json-number"),
    pytest.param(b'"hello"', id="json-string"),
    pytest.param(b"null", id="json-null"),
    pytest.param(b'{"records":"abcd"}', id="records-not-a-list"),
    pytest.param(b'{"records":[1,2,3]}', id="entries-not-objects"),
    pytest.param(b'{"records":[{"id":"0001"}]}', id="entry-missing-hash"),
    pytest.param(b'{"records":[{"sha256":"aa"}]}', id="entry-missing-id"),
    pytest.param(b'{"records":[{"id":"1","sha256":1}]}', id="hash-not-a-string"),
    pytest.param(b"\xff\xfe not json at all", id="not-json"),
    pytest.param(b"", id="empty"),
]


def attach_manifest(pdf_bytes, payload):
    """Put an arbitrary payload into the PDF under the manifest's name."""
    import pikepdf

    pdf = pikepdf.open(io.BytesIO(pdf_bytes))
    pdf.attachments[MANIFEST_FILENAME] = pikepdf.AttachedFileSpec(pdf, payload)
    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


class TestHostileManifest:
    """
    The manifest arrives inside an uploaded file, so it is attacker-controlled.
    Each of these used to raise out of verify_bytes and become an HTTP 500.
    """

    @pytest.mark.parametrize("payload", HOSTILE_MANIFESTS)
    def test_verification_does_not_crash(self, sample_pdf, settings, payload):
        report = verify_bytes(attach_manifest(sample_pdf, payload), settings)
        assert report["verdict"] == "FAIL"

    @pytest.mark.parametrize("payload", HOSTILE_MANIFESTS)
    def test_reading_the_manifest_raises_a_typed_error(self, sample_pdf, payload):
        with pytest.raises(ManifestError):
            read_manifest(attach_manifest(sample_pdf, payload))

    def test_a_wellformed_manifest_still_reads(self, sample_pdf, settings):
        sealed, _ = seal_bytes(sample_pdf, settings)
        assert read_manifest(sealed)["record_count"] == 6


# ---------------------------------------------------------------------------
# 5. Duplicate record numbers
# ---------------------------------------------------------------------------
class TestDuplicateRecordIds:
    """
    Records are matched by number. Two records sharing a number meant one was
    silently never checked, while the report claimed full coverage.
    """

    @pytest.fixture
    def duplicated(self):
        records = sample_records()[:2]
        records[0].id = "0001"
        records[0].body = "I agree to pay the full deposit."
        records[1].id = "0001"
        records[1].body = "Real message: I never agreed to that."
        return render_records_pdf(records, title="Duplicated numbering")

    def test_sealing_a_duplicate_numbered_export_is_refused(
        self, duplicated, settings
    ):
        from verifier import SealError

        with pytest.raises(SealError, match="more than once"):
            seal_bytes(duplicated, settings)

    def test_duplicates_introduced_after_sealing_are_reported(self):
        """
        The verification-time case: a properly numbered export is sealed, then
        someone renumbers one record so it collides with another. Keying by
        number meant the collided record vanished from the comparison instead
        of being flagged.
        """
        from verifier.manifest import build_manifest, compare_records

        records = sample_records()[:3]
        manifest = build_manifest(records)

        records[2].id = records[1].id  # renumber to collide

        result = compare_records(manifest, records)
        assert result["duplicate_ids"] == [records[1].id]
        assert result["all_records_match"] is False


# ---------------------------------------------------------------------------
# 6. Oversized uploads
# ---------------------------------------------------------------------------
class TestUploadIsBoundedBeforeItIsRead:
    """
    The size check used to run after the whole body had been parsed and spooled
    to disk, so the limit bounded nothing.
    """

    @pytest.fixture
    def client(self, settings, monkeypatch, tmp_path):
        import importlib
        import tempfile

        import web.app

        monkeypatch.setenv("COMMCHECKER_MAX_UPLOAD_MB", "2")
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
        importlib.reload(web.app)

        from fastapi.testclient import TestClient

        return TestClient(web.app.app), tmp_path

    def test_an_oversized_upload_is_refused(self, client):
        c, _ = client
        response = c.post(
            "/verify",
            files={"file": ("big.pdf", b"x" * (6 * 1024 * 1024), "application/pdf")},
        )
        assert response.status_code == 413

    def test_an_oversized_upload_is_never_written_to_disk(self, client):
        c, tmp_path = client
        before = set(p.name for p in tmp_path.iterdir())
        c.post(
            "/verify",
            files={"file": ("big.pdf", b"x" * (6 * 1024 * 1024), "application/pdf")},
        )
        assert set(p.name for p in tmp_path.iterdir()) == before

    def test_an_accepted_upload_is_not_written_to_disk(self, client):
        """Real exports exceed the 1 MB default spool, so this is the common case."""
        c, tmp_path = client
        before = set(p.name for p in tmp_path.iterdir())
        response = c.post(
            "/verify",
            files={
                "file": (
                    "ok.pdf",
                    b"%PDF-1.7\n" + b"y" * (1500 * 1024),
                    "application/pdf",
                )
            },
        )
        assert response.status_code == 200
        assert set(p.name for p in tmp_path.iterdir()) == before

    def test_a_hostile_manifest_returns_a_verdict_not_a_500(self, client, sample_pdf):
        c, _ = client
        payload = attach_manifest(sample_pdf, b'{"records":[{"id":"0001"}]}')
        response = c.post(
            "/verify", files={"file": ("x.pdf", payload, "application/pdf")}
        )
        assert response.status_code == 200
        assert response.json()["verdict"] == "FAIL"


# ---------------------------------------------------------------------------
# 7. A mistyped mode must not silently become demo mode
# ---------------------------------------------------------------------------
class TestModeTypo:
    def test_an_unrecognised_mode_is_rejected_before_verifying(
        self, clean_env, monkeypatch
    ):
        """COMMCHECKER_MODE=prod used to fall through to demo trust silently."""
        monkeypatch.setenv("COMMCHECKER_MODE", "prod")
        settings = load_settings()
        assert settings.validate() != []
        with pytest.raises(ConfigError):
            settings.require_valid()
