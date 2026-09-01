"""
CommChecker configuration.

Every knob lives here, and every knob is set the same way: an environment
variable starting with ``COMMCHECKER_``. Nothing is hard-coded, so moving from
the local demo to production is a matter of changing settings, not code.

Read CONFIGURATION.md for the plain-English version of this file.
"""
import base64
import binascii
import os
from dataclasses import dataclass, field
from typing import List, Optional

# ---------------------------------------------------------------------------
# Defaults. Chosen so that "no configuration at all" gives a working local demo.
# ---------------------------------------------------------------------------
DEFAULT_DEMO_P12 = "demo.p12"
DEFAULT_DEMO_PASSWORD = "demo"
DEFAULT_TSA_URL = "http://timestamp.digicert.com"
DEFAULT_TSA_TIMEOUT = 10
DEFAULT_MAX_UPLOAD_MB = 25

MODE_DEMO = "demo"
MODE_PRODUCTION = "production"


class ConfigError(Exception):
    """Raised when the configuration cannot produce a usable signing setup."""


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read COMMCHECKER_<name>. Blank or whitespace-only counts as 'not set'."""
    raw = os.environ.get(f"COMMCHECKER_{name}")
    if raw is None:
        return default
    raw = raw.strip()
    return raw if raw else default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(
            f"COMMCHECKER_{name} must be a whole number, got {raw!r}."
        )


@dataclass
class Settings:
    """A snapshot of the configuration, read once at startup."""

    # Which certificate world are we in?
    mode: str = MODE_DEMO

    # Production signing certificate (the one you buy from a CA).
    p12_path: Optional[str] = None
    p12_base64: Optional[str] = None
    p12_password: Optional[str] = None
    extra_chain_path: Optional[str] = None

    # Demo signing certificate (self-signed, local testing only).
    demo_p12_path: str = DEFAULT_DEMO_P12
    demo_p12_password: str = DEFAULT_DEMO_PASSWORD
    demo_p12_base64: Optional[str] = None

    # RFC-3161 trusted timestamp.
    tsa_url: Optional[str] = DEFAULT_TSA_URL
    tsa_username: Optional[str] = None
    tsa_password: Optional[str] = None
    tsa_timeout: int = DEFAULT_TSA_TIMEOUT
    tsa_required: bool = False

    # Trust settings used when verifying.
    trust_roots_path: Optional[str] = None
    trust_system_roots: bool = False
    allow_fetching: bool = False

    # Manifest behaviour.
    manifest_previews: bool = True

    # Web service.
    max_upload_mb: int = DEFAULT_MAX_UPLOAD_MB

    # Problems found while reading the environment (surfaced, never swallowed).
    problems: List[str] = field(default_factory=list)

    # -- derived helpers ---------------------------------------------------

    @property
    def is_production(self) -> bool:
        return self.mode == MODE_PRODUCTION

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def timestamping_enabled(self) -> bool:
        return bool(self.tsa_url)

    def describe(self) -> dict:
        """A redacted summary, safe to show in a UI or a log. No secrets."""
        return {
            "mode": self.mode,
            "signing_certificate": (
                "production (.p12 supplied)"
                if self.is_production
                else "demo self-signed (supplied)"
                if self.demo_p12_base64
                else f"demo self-signed ({self.demo_p12_path})"
            ),
            "certificate_source": self._cert_source_label(),
            "timestamp_authority": self.tsa_url or "disabled",
            "timestamp_required": self.tsa_required,
            "trust_roots": self.trust_roots_path or "none configured",
            "trust_system_roots": self.trust_system_roots,
            "revocation_checking": self.allow_fetching,
            "manifest_previews": self.manifest_previews,
            "max_upload_mb": self.max_upload_mb,
            "signing_key_present": bool(
                self.p12_path or self.p12_base64 or not self.is_production
            ),
            "problems": self.problems,
        }

    def _cert_source_label(self) -> str:
        if not self.is_production:
            if self.demo_p12_base64:
                return "COMMCHECKER_DEMO_P12_BASE64 (in memory)"
            return f"demo file: {self.demo_p12_path}"
        if self.p12_base64:
            return "COMMCHECKER_P12_BASE64 (in memory)"
        if self.p12_path:
            return f"file: {self.p12_path}"
        return "not configured"

    # -- validation --------------------------------------------------------

    def validate(self, for_signing: bool = False) -> List[str]:
        """
        Return a list of configuration problems in plain English.

        An empty list means the configuration is usable.

        ``for_signing`` adds the checks that only matter when this machine is
        going to APPLY a seal. Verifying needs no private key - it needs to
        know which authorities to trust - so a verifier is not asked for one.
        That separation is deliberate: the signing key should never have to sit
        on an internet-facing box just to satisfy a config check.
        """
        problems = list(self.problems)

        if self.mode not in (MODE_DEMO, MODE_PRODUCTION):
            problems.append(
                f"COMMCHECKER_MODE must be 'demo' or 'production', got "
                f"{self.mode!r}."
            )
            return problems

        if self.is_production:
            if for_signing:
                if not self.p12_path and not self.p12_base64:
                    problems.append(
                        "Sealing in production needs a real signing "
                        "certificate. Set COMMCHECKER_P12_PATH to your .p12 "
                        "file (or COMMCHECKER_P12_BASE64 if your host has no "
                        "file storage)."
                    )
                if self.p12_path and self.p12_base64:
                    problems.append(
                        "Set either COMMCHECKER_P12_PATH or "
                        "COMMCHECKER_P12_BASE64, not both."
                    )
                if self.p12_path and not os.path.exists(self.p12_path):
                    problems.append(
                        f"The signing certificate file was not found at "
                        f"{self.p12_path!r}."
                    )
                if self.p12_password is None:
                    problems.append(
                        "Sealing in production needs the certificate password. "
                        "Set COMMCHECKER_P12_PASSWORD or "
                        "COMMCHECKER_P12_PASSWORD_FILE."
                    )
            if not self.trust_roots_path and not self.trust_system_roots:
                problems.append(
                    "Production mode has no trust roots, so CommChecker could "
                    "not confirm who sealed any document and would fail every "
                    "check. Set COMMCHECKER_TRUST_SYSTEM_ROOTS=1 (usual "
                    "choice), or point COMMCHECKER_TRUST_ROOTS at your CA "
                    "certificate."
                )
            if self.tsa_required and not self.tsa_url:
                problems.append(
                    "COMMCHECKER_TSA_REQUIRED is on but COMMCHECKER_TSA_URL is "
                    "empty. Either set a timestamp authority URL or turn the "
                    "requirement off."
                )

        if self.trust_roots_path and not os.path.exists(self.trust_roots_path):
            problems.append(
                f"COMMCHECKER_TRUST_ROOTS points at {self.trust_roots_path!r}, "
                f"which does not exist."
            )

        if self.max_upload_mb <= 0:
            problems.append("COMMCHECKER_MAX_UPLOAD_MB must be greater than 0.")

        return problems

    def require_valid(self, for_signing: bool = False) -> None:
        """Raise ConfigError listing every problem at once."""
        problems = self.validate(for_signing=for_signing)
        if problems:
            bullets = "\n".join(f"  - {p}" for p in problems)
            raise ConfigError(
                "CommChecker is not configured correctly:\n" + bullets
            )

    # -- the signing certificate -------------------------------------------

    def signing_p12_bytes(self) -> bytes:
        """
        Return the raw PKCS#12 bytes to sign with.

        In production this is your CA-issued certificate and it is an error to
        fall back to the demo certificate: a production seal signed by a
        self-signed demo key would look valid to this tool while being worthless
        to Adobe, a court, or a counterparty.
        """
        if self.is_production:
            if self.p12_base64:
                try:
                    return base64.b64decode(self.p12_base64, validate=True)
                except (binascii.Error, ValueError) as e:
                    raise ConfigError(
                        "COMMCHECKER_P12_BASE64 is not valid base64 text: "
                        f"{e}"
                    )
            if not self.p12_path:
                raise ConfigError(
                    "Production mode is on but no signing certificate is "
                    "configured. Set COMMCHECKER_P12_PATH."
                )
            try:
                with open(self.p12_path, "rb") as f:
                    return f.read()
            except OSError as e:
                raise ConfigError(
                    f"Could not read the signing certificate at "
                    f"{self.p12_path!r}: {e}"
                )

        # Demo mode.
        if self.demo_p12_base64:
            # A hosted demo needs the SAME demo certificate as the machine that
            # sealed the documents, otherwise every upload is correctly - and
            # unhelpfully - rejected as coming from an unknown signer.
            try:
                return base64.b64decode(self.demo_p12_base64, validate=True)
            except (binascii.Error, ValueError) as e:
                raise ConfigError(
                    f"COMMCHECKER_DEMO_P12_BASE64 is not valid base64 text: {e}"
                )
        if not os.path.exists(self.demo_p12_path):
            raise ConfigError(
                f"The demo certificate {self.demo_p12_path!r} does not exist "
                f"yet. Create it with:  python cli.py init"
            )
        with open(self.demo_p12_path, "rb") as f:
            return f.read()

    def signing_password(self) -> bytes:
        if self.is_production:
            if self.p12_password is None:
                raise ConfigError(
                    "Production mode is on but no certificate password is set. "
                    "Set COMMCHECKER_P12_PASSWORD or "
                    "COMMCHECKER_P12_PASSWORD_FILE."
                )
            return self.p12_password.encode("utf-8")
        return self.demo_p12_password.encode("utf-8")


def load_settings(env_prefix_check: bool = True) -> Settings:
    """Build a Settings object from the current environment variables."""
    problems: List[str] = []

    mode = (_env("MODE", MODE_DEMO) or MODE_DEMO).lower()

    # The password may be given directly or pointed at a file. A file is the
    # safer option on servers: secrets managers mount secrets as files.
    password = _env("P12_PASSWORD")
    password_file = _env("P12_PASSWORD_FILE")
    if password_file:
        try:
            with open(password_file, "r", encoding="utf-8") as f:
                # Trailing newlines are almost always an accident of the editor,
                # not part of the password.
                password = f.read().rstrip("\r\n")
        except OSError as e:
            problems.append(
                f"COMMCHECKER_P12_PASSWORD_FILE could not be read "
                f"({password_file!r}): {e}"
            )

    is_production = mode == MODE_PRODUCTION

    try:
        tsa_timeout = _env_int("TSA_TIMEOUT", DEFAULT_TSA_TIMEOUT)
    except ConfigError as e:
        problems.append(str(e))
        tsa_timeout = DEFAULT_TSA_TIMEOUT

    try:
        max_upload_mb = _env_int("MAX_UPLOAD_MB", DEFAULT_MAX_UPLOAD_MB)
    except ConfigError as e:
        problems.append(str(e))
        max_upload_mb = DEFAULT_MAX_UPLOAD_MB

    # An explicitly empty TSA URL disables timestamping; unset means "default".
    tsa_url_raw = os.environ.get("COMMCHECKER_TSA_URL")
    if tsa_url_raw is not None and not tsa_url_raw.strip():
        tsa_url: Optional[str] = None
    else:
        tsa_url = _env("TSA_URL", DEFAULT_TSA_URL)

    settings = Settings(
        mode=mode,
        p12_path=_env("P12_PATH"),
        p12_base64=_env("P12_BASE64"),
        p12_password=password,
        extra_chain_path=_env("P12_CHAIN_PATH"),
        demo_p12_path=_env("DEMO_P12_PATH", DEFAULT_DEMO_P12),
        demo_p12_password=_env("DEMO_P12_PASSWORD", DEFAULT_DEMO_PASSWORD),
        demo_p12_base64=_env("DEMO_P12_BASE64"),
        tsa_url=tsa_url,
        tsa_username=_env("TSA_USERNAME"),
        tsa_password=_env("TSA_PASSWORD"),
        tsa_timeout=tsa_timeout,
        # A production seal without a timestamp is weak, so the requirement
        # defaults on there and off for local demos (which may be offline).
        tsa_required=_env_bool("TSA_REQUIRED", is_production),
        trust_roots_path=_env("TRUST_ROOTS"),
        trust_system_roots=_env_bool("TRUST_SYSTEM_ROOTS", is_production),
        allow_fetching=_env_bool("ALLOW_FETCHING", False),
        manifest_previews=_env_bool("MANIFEST_PREVIEWS", True),
        max_upload_mb=max_upload_mb,
        problems=problems,
    )
    return settings


def quiet_library_logs() -> None:
    """
    Turn down the cryptography libraries' logging.

    An untrusted or self-signed certificate is a normal, expected outcome for
    this tool - it is a finding we report, not a crash. Left alone, the
    underlying libraries print full stack traces for it, which looks like a
    catastrophe to anyone reading the console. Call this from entry points
    (the CLI, the web service), never from library code.
    """
    import logging

    for name in (
        "pyhanko_certvalidator",
        "pyhanko.sign.validation",
        "pyhanko.sign.validation.generic_cms",
        "pyhanko.sign.diff_analysis",
    ):
        logging.getLogger(name).setLevel(logging.CRITICAL)
