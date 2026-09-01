"""
A local RFC-3161 timestamp authority, for tests.

Real timestamp authorities need the internet. The test suite must be able to
prove the timestamp path works without it, so this builds a throwaway TSA
certificate and hands back a timestamper that signs with it offline.

The code path exercised is the same one a production TSA drives - only the
transport differs.
"""
import datetime

from asn1crypto import keys as asn1_keys
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from pyhanko.sign.timestamps.dummy_client import DummyTimeStamper
from pyhanko_certvalidator.registry import SimpleCertificateStore


def make_local_tsa(fixed_time=None):
    """
    Return (timestamper, tsa_certificate).

    The certificate is what a verifier needs as a trust root to consider the
    timestamp trustworthy, so tests can check both the trusted and untrusted
    branches.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "CommChecker Test TSA")]
    )
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
            x509.BasicConstraints(ca=True, path_length=None), critical=True
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        # A timestamp authority certificate must carry this EKU, critically.
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )

    asn1_cert = asn1_x509.Certificate.load(
        cert.public_bytes(serialization.Encoding.DER)
    )
    asn1_key = asn1_keys.PrivateKeyInfo.load(
        key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    store = SimpleCertificateStore()
    store.register(asn1_cert)

    timestamper = DummyTimeStamper(
        tsa_cert=asn1_cert,
        tsa_key=asn1_key,
        certs_to_embed=store,
        fixed_dt=fixed_time,
    )
    return timestamper, cert


def write_pem(cert, path) -> str:
    """Write a certificate out as PEM so it can be used as a trust root file."""
    with open(path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    return str(path)
