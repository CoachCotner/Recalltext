"""
The RFC-3161 trusted timestamp.

A real timestamp authority needs the internet, which a test suite must not.
These tests drive the same code path with a local authority (see tsa_helper),
so the timestamp behaviour is genuinely exercised offline.
"""
import datetime

import pytest

from verifier import SealError, load_settings, seal_bytes, verify_bytes
from verifier.sealing import build_timestamper
from tsa_helper import make_local_tsa, write_pem

FIXED_TIME = datetime.datetime(2025, 8, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)


@pytest.fixture
def tsa():
    return make_local_tsa(fixed_time=FIXED_TIME)


class TestTimestampIsApplied:
    def test_sealing_reports_that_it_timestamped(self, sample_pdf, settings, tsa):
        timestamper, _ = tsa
        _, info = seal_bytes(sample_pdf, settings, timestamper=timestamper)
        assert info["timestamped"] is True

    def test_the_timestamp_is_present_on_the_seal(self, sample_pdf, settings, tsa):
        timestamper, _ = tsa
        sealed, _ = seal_bytes(sample_pdf, settings, timestamper=timestamper)
        assert verify_bytes(sealed, settings)["timestamp"]["present"] is True

    def test_the_recorded_time_is_the_authority_s_time(
        self, sample_pdf, settings, tsa
    ):
        """The time comes from the authority, not from the signing computer."""
        timestamper, _ = tsa
        sealed, _ = seal_bytes(sample_pdf, settings, timestamper=timestamper)
        report = verify_bytes(sealed, settings)
        assert report["timestamp"]["time_utc"].startswith("2025-08-15T12:00:00")

    def test_the_timestamp_is_intact(self, sample_pdf, settings, tsa):
        timestamper, _ = tsa
        sealed, _ = seal_bytes(sample_pdf, settings, timestamper=timestamper)
        assert verify_bytes(sealed, settings)["timestamp"]["intact"] is True


class TestTimestampTrust:
    def test_an_unknown_authority_is_not_trusted(self, sample_pdf, settings, tsa):
        """Without its root loaded, the authority cannot be vouched for."""
        timestamper, _ = tsa
        sealed, _ = seal_bytes(sample_pdf, settings, timestamper=timestamper)
        report = verify_bytes(sealed, settings)
        assert report["timestamp"]["present"] is True
        assert report["timestamp"]["trusted"] is False

    def test_a_known_authority_is_trusted(
        self, sample_pdf, settings, tsa, tmp_path, monkeypatch
    ):
        timestamper, tsa_cert = tsa
        sealed, _ = seal_bytes(sample_pdf, settings, timestamper=timestamper)

        pem = write_pem(tsa_cert, tmp_path / "tsa.pem")
        monkeypatch.setenv("COMMCHECKER_TRUST_ROOTS", pem)

        report = verify_bytes(sealed, load_settings())
        assert report["timestamp"]["trusted"] is True

    def test_trusting_the_tsa_does_not_break_the_demo_signer(
        self, sample_pdf, settings, tsa, tmp_path, monkeypatch
    ):
        """
        Regression: configuring trust roots for the timestamp authority must
        not make the demo signing certificate look untrusted and flip a clean
        document to FAIL.
        """
        timestamper, tsa_cert = tsa
        sealed, _ = seal_bytes(sample_pdf, settings, timestamper=timestamper)

        pem = write_pem(tsa_cert, tmp_path / "tsa.pem")
        monkeypatch.setenv("COMMCHECKER_TRUST_ROOTS", pem)

        assert verify_bytes(sealed, load_settings())["verdict"] == "PASS"


class TestWithoutATimestamp:
    def test_an_untimestamped_seal_still_verifies(self, sample_pdf, settings):
        sealed, info = seal_bytes(sample_pdf, settings)
        assert info["timestamped"] is False
        assert verify_bytes(sealed, settings)["verdict"] == "PASS"

    def test_the_missing_timestamp_is_called_out(self, sample_pdf, settings):
        sealed, _ = seal_bytes(sample_pdf, settings)
        report = verify_bytes(sealed, settings)
        assert report["timestamp"]["present"] is False
        assert any("timestamp" in w.lower() for w in report["warnings"])


class TestTimestampFailureHandling:
    class BrokenTimeStamper:
        """Stands in for an authority that is down or unreachable."""

        url = "http://tsa.example.invalid"

        async def async_timestamp(self, *args, **kwargs):
            raise IOError("timestamp authority unreachable")

        def timestamp(self, *args, **kwargs):
            raise IOError("timestamp authority unreachable")

    def test_optional_timestamping_falls_back_to_an_unstamped_seal(
        self, sample_pdf, settings
    ):
        """A local demo on a plane should still seal."""
        settings.tsa_required = False
        sealed, info = seal_bytes(
            sample_pdf, settings, timestamper=self.BrokenTimeStamper()
        )
        assert info["timestamped"] is False
        assert "NOT timestamped" in info["timestamp_note"]
        assert verify_bytes(sealed, settings)["verdict"] == "PASS"

    def test_required_timestamping_refuses_to_seal_without_one(
        self, sample_pdf, settings
    ):
        """
        In production a seal without a trusted time is worth much less, so
        COMMCHECKER_TSA_REQUIRED makes the failure loud instead of silent.
        """
        settings.tsa_required = True
        settings.tsa_url = "http://tsa.example.invalid"
        with pytest.raises(SealError, match="timestamp"):
            seal_bytes(sample_pdf, settings, timestamper=self.BrokenTimeStamper())


class TestTimestamperConfiguration:
    def test_no_url_means_no_timestamper(self, settings):
        settings.tsa_url = None
        assert build_timestamper(settings) is None

    def test_a_url_builds_a_client(self, settings):
        settings.tsa_url = "http://timestamp.example.com"
        assert build_timestamper(settings) is not None

    def test_credentials_are_passed_through(self, settings):
        settings.tsa_url = "https://tsa.example.com"
        settings.tsa_username = "acct"
        settings.tsa_password = "secret"
        assert build_timestamper(settings) is not None
