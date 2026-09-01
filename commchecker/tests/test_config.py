"""
Configuration: swapping the demo certificate for a real one.

The safety property under test throughout: production mode must never quietly
fall back to the demo certificate. A seal that looks valid to this tool but is
signed by a self-signed demo key is worse than no seal at all.
"""
import base64

import pytest

from verifier import ConfigError, load_settings, seal_bytes, verify_bytes
from verifier.certs import load_signer, make_demo_cert
from verifier.config import MODE_DEMO, MODE_PRODUCTION


@pytest.fixture
def real_cert(tmp_path):
    """
    Stands in for a certificate bought from a Certificate Authority.

    Structurally it is what a CA hands you: a .p12 holding a key and a
    certificate, protected by a password.
    """
    path = tmp_path / "production.p12"
    make_demo_cert(str(path), password="s3cret-passphrase")
    return str(path)


class TestDefaults:
    def test_no_configuration_gives_a_working_demo(self, clean_env):
        settings = load_settings()
        assert settings.mode == MODE_DEMO
        assert settings.validate() == []

    def test_demo_mode_does_not_require_a_certificate_file_up_front(self, clean_env):
        assert load_settings().validate() == []


class TestProductionCertificate:
    def test_production_uses_the_configured_certificate(
        self, clean_env, monkeypatch, real_cert
    ):
        monkeypatch.setenv("COMMCHECKER_MODE", "production")
        monkeypatch.setenv("COMMCHECKER_P12_PATH", real_cert)
        monkeypatch.setenv("COMMCHECKER_P12_PASSWORD", "s3cret-passphrase")
        monkeypatch.setenv("COMMCHECKER_TSA_REQUIRED", "0")

        settings = load_settings()
        assert settings.validate() == []
        assert load_signer(settings) is not None

    def test_production_without_a_certificate_is_refused(self, clean_env, monkeypatch):
        monkeypatch.setenv("COMMCHECKER_MODE", "production")
        problems = load_settings().validate()
        assert any("signing certificate" in p for p in problems)

    def test_production_never_falls_back_to_the_demo_certificate(
        self, clean_env, monkeypatch
    ):
        """The single most important safety property in this file."""
        make_demo_cert("demo.p12", "demo")
        monkeypatch.setenv("COMMCHECKER_MODE", "production")
        settings = load_settings()
        with pytest.raises(ConfigError):
            load_signer(settings)

    def test_a_missing_certificate_file_is_reported_clearly(
        self, clean_env, monkeypatch
    ):
        monkeypatch.setenv("COMMCHECKER_MODE", "production")
        monkeypatch.setenv("COMMCHECKER_P12_PATH", "/no/such/cert.p12")
        monkeypatch.setenv("COMMCHECKER_P12_PASSWORD", "x")
        assert any("was not found" in p for p in load_settings().validate())

    def test_a_wrong_password_is_reported_clearly(
        self, clean_env, monkeypatch, real_cert
    ):
        monkeypatch.setenv("COMMCHECKER_MODE", "production")
        monkeypatch.setenv("COMMCHECKER_P12_PATH", real_cert)
        monkeypatch.setenv("COMMCHECKER_P12_PASSWORD", "the-wrong-password")
        monkeypatch.setenv("COMMCHECKER_TSA_REQUIRED", "0")
        with pytest.raises(ConfigError, match="password"):
            load_signer(load_settings())

    def test_the_password_can_come_from_a_file(
        self, clean_env, monkeypatch, real_cert, tmp_path
    ):
        """Secret managers mount secrets as files, not environment variables."""
        secret = tmp_path / "cert-password.txt"
        secret.write_text("s3cret-passphrase\n")  # trailing newline is an accident

        monkeypatch.setenv("COMMCHECKER_MODE", "production")
        monkeypatch.setenv("COMMCHECKER_P12_PATH", real_cert)
        monkeypatch.setenv("COMMCHECKER_P12_PASSWORD_FILE", str(secret))
        monkeypatch.setenv("COMMCHECKER_TSA_REQUIRED", "0")

        settings = load_settings()
        assert settings.validate() == []
        assert load_signer(settings) is not None

    def test_the_certificate_can_come_from_base64(
        self, clean_env, monkeypatch, real_cert
    ):
        """For hosts with no persistent filesystem."""
        with open(real_cert, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()

        monkeypatch.setenv("COMMCHECKER_MODE", "production")
        monkeypatch.setenv("COMMCHECKER_P12_BASE64", encoded)
        monkeypatch.setenv("COMMCHECKER_P12_PASSWORD", "s3cret-passphrase")
        monkeypatch.setenv("COMMCHECKER_TSA_REQUIRED", "0")

        settings = load_settings()
        assert settings.validate() == []
        assert load_signer(settings) is not None

    def test_bad_base64_is_reported_clearly(self, clean_env, monkeypatch):
        monkeypatch.setenv("COMMCHECKER_MODE", "production")
        monkeypatch.setenv("COMMCHECKER_P12_BASE64", "!!! not base64 !!!")
        monkeypatch.setenv("COMMCHECKER_P12_PASSWORD", "x")
        monkeypatch.setenv("COMMCHECKER_TSA_REQUIRED", "0")
        with pytest.raises(ConfigError, match="base64"):
            load_signer(load_settings())

    def test_both_certificate_sources_at_once_is_refused(
        self, clean_env, monkeypatch, real_cert
    ):
        monkeypatch.setenv("COMMCHECKER_MODE", "production")
        monkeypatch.setenv("COMMCHECKER_P12_PATH", real_cert)
        monkeypatch.setenv("COMMCHECKER_P12_BASE64", "abcd")
        monkeypatch.setenv("COMMCHECKER_P12_PASSWORD", "x")
        assert any("not both" in p for p in load_settings().validate())


class TestSealingWithAProductionCertificate:
    def test_a_real_certificate_produces_a_verifiable_seal(
        self, clean_env, monkeypatch, real_cert, sample_pdf, tmp_path
    ):
        """End to end with a CA-shaped certificate instead of the demo one."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.serialization import pkcs12

        monkeypatch.setenv("COMMCHECKER_MODE", "production")
        monkeypatch.setenv("COMMCHECKER_P12_PATH", real_cert)
        monkeypatch.setenv("COMMCHECKER_P12_PASSWORD", "s3cret-passphrase")
        monkeypatch.setenv("COMMCHECKER_TSA_REQUIRED", "0")

        settings = load_settings()
        sealed, info = seal_bytes(sample_pdf, settings)
        assert info["signing_mode"] == "production"

        # Trust that certificate the way a real deployment trusts its CA root.
        with open(real_cert, "rb") as f:
            _, cert, _ = pkcs12.load_key_and_certificates(
                f.read(), b"s3cret-passphrase"
            )
        pem = tmp_path / "ca.pem"
        pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        monkeypatch.setenv("COMMCHECKER_TRUST_ROOTS", str(pem))

        report = verify_bytes(sealed, load_settings())
        assert report["verdict"] == "PASS"

    def test_an_untrusted_signer_does_not_pass_in_production(
        self, clean_env, monkeypatch, real_cert, sample_pdf, tmp_path
    ):
        """A seal from a certificate we do not trust must not show green."""
        monkeypatch.setenv("COMMCHECKER_MODE", "production")
        monkeypatch.setenv("COMMCHECKER_P12_PATH", real_cert)
        monkeypatch.setenv("COMMCHECKER_P12_PASSWORD", "s3cret-passphrase")
        monkeypatch.setenv("COMMCHECKER_TSA_REQUIRED", "0")
        settings = load_settings()
        sealed, _ = seal_bytes(sample_pdf, settings)

        # Trust roots that do not include the signer.
        other = tmp_path / "unrelated.p12"
        make_demo_cert(str(other), "x")
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.serialization import pkcs12

        with open(other, "rb") as f:
            _, cert, _ = pkcs12.load_key_and_certificates(f.read(), b"x")
        pem = tmp_path / "unrelated.pem"
        pem.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        monkeypatch.setenv("COMMCHECKER_TRUST_ROOTS", str(pem))

        assert verify_bytes(sealed, load_settings())["verdict"] == "FAIL"


class TestOtherSettings:
    def test_the_timestamp_authority_is_configurable(self, clean_env, monkeypatch):
        monkeypatch.setenv("COMMCHECKER_TSA_URL", "https://tsa.example.com/tsr")
        assert load_settings().tsa_url == "https://tsa.example.com/tsr"

    def test_an_empty_timestamp_url_disables_timestamping(self, clean_env, monkeypatch):
        monkeypatch.setenv("COMMCHECKER_TSA_URL", "")
        settings = load_settings()
        assert settings.tsa_url is None
        assert settings.timestamping_enabled is False

    def test_timestamps_are_required_by_default_in_production(
        self, clean_env, monkeypatch
    ):
        monkeypatch.setenv("COMMCHECKER_MODE", "production")
        assert load_settings().tsa_required is True

    def test_timestamps_are_optional_by_default_in_demo(self, clean_env):
        assert load_settings().tsa_required is False

    def test_the_upload_limit_is_configurable(self, clean_env, monkeypatch):
        monkeypatch.setenv("COMMCHECKER_MAX_UPLOAD_MB", "5")
        assert load_settings().max_upload_bytes == 5 * 1024 * 1024

    def test_a_nonsense_number_is_reported_not_crashed(self, clean_env, monkeypatch):
        monkeypatch.setenv("COMMCHECKER_MAX_UPLOAD_MB", "lots")
        assert any("whole number" in p for p in load_settings().validate())

    def test_an_unknown_mode_is_rejected(self, clean_env, monkeypatch):
        monkeypatch.setenv("COMMCHECKER_MODE", "staging")
        assert any("demo" in p and "production" in p for p in load_settings().validate())

    def test_previews_can_be_switched_off(self, clean_env, monkeypatch):
        monkeypatch.setenv("COMMCHECKER_MANIFEST_PREVIEWS", "0")
        assert load_settings().manifest_previews is False

    def test_describe_never_leaks_the_password(
        self, clean_env, monkeypatch, real_cert
    ):
        monkeypatch.setenv("COMMCHECKER_MODE", "production")
        monkeypatch.setenv("COMMCHECKER_P12_PATH", real_cert)
        monkeypatch.setenv("COMMCHECKER_P12_PASSWORD", "s3cret-passphrase")
        assert "s3cret-passphrase" not in str(load_settings().describe())

    def test_describe_never_leaks_a_base64_certificate(
        self, clean_env, monkeypatch
    ):
        monkeypatch.setenv("COMMCHECKER_MODE", "production")
        monkeypatch.setenv("COMMCHECKER_P12_BASE64", "SECRETKEYMATERIAL")
        monkeypatch.setenv("COMMCHECKER_P12_PASSWORD", "x")
        assert "SECRETKEYMATERIAL" not in str(load_settings().describe())
