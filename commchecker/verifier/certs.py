"""
Certificates: creating the demo one, loading the real one, and deciding what to
trust when verifying.

Two separate jobs live here, and it matters that you keep them straight:

  SIGNING  - the private key that applies the seal. One certificate, yours.
  TRUST    - the list of authorities you are willing to believe when checking
             somebody else's seal. Usually the public CA roots.
"""
import datetime
import os
from typing import List, Optional, Tuple

from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from pyhanko.sign import signers
from pyhanko.sign.general import load_certs_from_pemder
from pyhanko_certvalidator import ValidationContext

from .config import ConfigError, Settings

DEMO_SUBJECT = "CommLocker Demo Signing (NOT FOR PRODUCTION)"


# ---------------------------------------------------------------------------
# Demo certificate
# ---------------------------------------------------------------------------
def make_demo_cert(path: str = "demo.p12", password: str = "demo") -> str:
    """
    Create a self-signed DEMO signing certificate.

    This is for local testing only. It is self-signed, which means nothing in
    the outside world trusts it: Adobe Reader will show a yellow warning, and a
    counterparty has no reason to believe it. Production uses a certificate
    issued by a real Certificate Authority - see CONFIGURATION.md.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, DEMO_SUBJECT)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CODE_SIGNING]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    blob = pkcs12.serialize_key_and_certificates(
        b"commlocker",
        key,
        cert,
        None,
        serialization.BestAvailableEncryption(password.encode("utf-8")),
    )
    with open(path, "wb") as f:
        f.write(blob)
    return path


def ensure_demo_cert(settings: Settings) -> str:
    """Create the demo certificate if it is missing. No-op in production."""
    if settings.is_production:
        return ""
    if not os.path.exists(settings.demo_p12_path):
        make_demo_cert(settings.demo_p12_path, settings.demo_p12_password)
    return settings.demo_p12_path


# ---------------------------------------------------------------------------
# Loading the signing key
# ---------------------------------------------------------------------------
def load_signer(settings: Settings) -> signers.SimpleSigner:
    """
    Load the signing certificate described by the settings.

    Raises ConfigError with an explanation a human can act on, rather than
    returning None and failing mysteriously three steps later.
    """
    settings.require_valid()
    p12_bytes = settings.signing_p12_bytes()
    password = settings.signing_password()

    other_certs = []
    if settings.extra_chain_path:
        try:
            other_certs = list(load_certs_from_pemder([settings.extra_chain_path]))
        except Exception as e:
            raise ConfigError(
                f"Could not read the intermediate certificate chain at "
                f"{settings.extra_chain_path!r}: {e}"
            )

    try:
        signer = signers.SimpleSigner.load_pkcs12_data(
            p12_bytes,
            passphrase=password,
            other_certs=other_certs or None,
        )
    except Exception as e:
        where = settings._cert_source_label()
        raise ConfigError(
            f"Could not open the signing certificate ({where}). The usual "
            f"cause is a wrong password. Underlying error: {e}"
        )
    if signer is None:
        raise ConfigError(
            "The signing certificate could not be loaded. Check the file and "
            "the password."
        )
    return signer


def describe_certificate(cert: asn1_x509.Certificate) -> dict:
    """Human-readable facts about a certificate, for the report."""
    if cert is None:
        return {}
    try:
        not_before = cert["tbs_certificate"]["validity"]["not_before"].native
        not_after = cert["tbs_certificate"]["validity"]["not_after"].native
    except Exception:
        not_before = not_after = None
    return {
        "subject": cert.subject.human_friendly,
        "issuer": cert.issuer.human_friendly,
        "serial": format(cert.serial_number, "x"),
        "valid_from": not_before.isoformat() if not_before else None,
        "valid_until": not_after.isoformat() if not_after else None,
        "self_signed": cert.subject.human_friendly == cert.issuer.human_friendly,
    }


# ---------------------------------------------------------------------------
# Trust roots (used when verifying)
# ---------------------------------------------------------------------------
def load_trust_roots(settings: Settings) -> Tuple[List[asn1_x509.Certificate], List[str]]:
    """
    Load the certificates we are willing to treat as trust anchors.

    Returns (certificates, notes) where notes explains what was loaded, so the
    report can be honest about which anchors were in play.
    """
    roots: List[asn1_x509.Certificate] = []
    notes: List[str] = []
    failures: List[str] = []

    path = settings.trust_roots_path
    if path:
        files = []
        if os.path.isdir(path):
            for entry in sorted(os.listdir(path)):
                if entry.lower().endswith((".pem", ".crt", ".cer", ".der")):
                    files.append(os.path.join(path, entry))
        else:
            files = [path]
        for f in files:
            try:
                loaded = list(load_certs_from_pemder([f]))
                roots.extend(loaded)
                notes.append(f"{len(loaded)} certificate(s) from {os.path.basename(f)}")
            except Exception as e:
                notes.append(f"could not read {os.path.basename(f)}: {e}")
                failures.append(f"{os.path.basename(f)}: {e}")

    if settings.trust_system_roots:
        system_roots, note = _load_system_roots()
        roots.extend(system_roots)
        notes.append(note)

    if failures and not roots:
        # A mangled CA bundle must not degrade quietly into "trust nothing",
        # which downstream would read as "could not evaluate".
        notes.append(
            "WARNING: no trust roots could be loaded - " + "; ".join(failures)
        )

    return roots, notes


def _load_system_roots() -> Tuple[List[asn1_x509.Certificate], str]:
    """
    Load the operating system's public CA bundle.

    This is what makes a real CA-issued seal verify without any manual setup:
    the CA that issued your certificate is already in this list.
    """
    candidates = [
        "/etc/ssl/certs/ca-certificates.crt",       # Debian/Ubuntu
        "/etc/pki/tls/certs/ca-bundle.crt",         # RHEL/Fedora
        "/etc/ssl/cert.pem",                        # Alpine/macOS
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                certs = list(load_certs_from_pemder([path]))
                return certs, f"{len(certs)} system root(s) from {path}"
            except Exception as e:
                return [], f"system roots at {path} could not be read: {e}"

    # Fall back to the certifi bundle if the OS has no bundle (some containers).
    try:
        import certifi

        certs = list(load_certs_from_pemder([certifi.where()]))
        return certs, f"{len(certs)} system root(s) from certifi"
    except Exception as e:
        return [], f"no system root store found: {e}"


def build_validation_context(
    settings: Settings,
    fallback_cert: Optional[asn1_x509.Certificate] = None,
) -> Tuple[ValidationContext, dict]:
    """
    Build the trust context used to check a seal, plus a description of it.

    Pass ``fallback_cert`` when building the context for the *signer*. In demo
    mode that certificate is added to the anchor set so the local demo shows a
    green light - but the description records the anchor as "demo-self-trust",
    so the report never presents it as real-world trust.

    Pass no fallback when building the context for the *timestamp*: a timestamp
    authority has to stand on its own roots or not at all.
    """
    roots, notes = load_trust_roots(settings)
    demo_self_trust = False

    if fallback_cert is not None and not settings.is_production:
        # Trusting our own demo certificate is circular, and labelled as such.
        roots = roots + [fallback_cert]
        demo_self_trust = True
        notes.append("demo mode - the demo certificate is trusted as its own anchor")

    if demo_self_trust:
        anchor_kind = "demo-self-trust"
    elif roots:
        anchor_kind = "configured"
    else:
        anchor_kind = "none"

    vc = ValidationContext(
        trust_roots=roots or None,
        allow_fetching=settings.allow_fetching,
        revocation_mode="soft-fail",
        # A seal is checked long after signing, so revocation info published
        # after the signing time still applies to it.
        retroactive_revinfo=True,
    )
    description = {
        "anchor_kind": anchor_kind,
        "root_count": len(roots),
        "notes": notes,
        "publicly_trusted": anchor_kind == "configured" and settings.trust_system_roots,
    }
    return vc, description
