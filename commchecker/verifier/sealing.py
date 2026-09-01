"""
Sealing: attach the manifest, sign the document, and stamp it with a trusted
time from an RFC-3161 timestamp authority.

Everything here works on bytes in memory. Nothing touches the disk.

Why the timestamp matters
-------------------------
A signature on its own proves *who* sealed the document. It does not prove
*when*: the signing computer's clock is whatever the signer says it is, and a
certificate that later expires or is revoked drags the signature down with it.

An RFC-3161 timestamp fixes that. We send the timestamp authority a hash of the
signature - never the document, never its contents - and it returns a signed
statement that this hash existed at that moment. Now the seal proves the
document existed in this exact form before that time, and it keeps proving it
after the signing certificate expires.
"""
import io
from typing import List, Optional, Tuple

from pyhanko.pdf_utils import embed
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers
from pyhanko.sign.fields import SigSeedSubFilter
from pyhanko.sign.signers import PdfSignatureMetadata
from pyhanko.sign.timestamps import HTTPTimeStamper

from .config import ConfigError, Settings, load_settings
from .certs import load_signer
from .coverpage import (
    TIMESTAMP_FILENAME,
    content_timestamp,
    find_cover_logo,
    prepend_cover,
    render_cover_page,
)
from .manifest import (
    MANIFEST_FILENAME,
    ManifestError,
    Record,
    build_manifest,
    extract_records,
    manifest_bytes,
)

SEAL_FIELD_NAME = "CommLockerSeal"
SEAL_REASON = "CommLocker integrity seal"


class SealError(Exception):
    """Sealing could not be completed."""


def build_timestamper(settings: Settings) -> Optional[HTTPTimeStamper]:
    """Create the RFC-3161 client, or None when timestamping is switched off."""
    if not settings.tsa_url:
        return None
    auth = None
    if settings.tsa_username:
        auth = (settings.tsa_username, settings.tsa_password or "")
    return HTTPTimeStamper(
        url=settings.tsa_url,
        https=settings.tsa_url.lower().startswith("https"),
        timeout=settings.tsa_timeout,
        auth=auth,
    )


def seal_bytes(
    pdf_bytes: bytes,
    settings: Optional[Settings] = None,
    records: Optional[List[Record]] = None,
    source: Optional[dict] = None,
    timestamper=None,
) -> Tuple[bytes, dict]:
    """
    Seal a PDF held in memory.

    Returns (sealed_pdf_bytes, info) where info describes what was done: how
    many records went into the manifest, and whether a trusted timestamp was
    obtained.

    Pass ``timestamper`` to override the configured timestamp authority. This
    is what the test suite uses to exercise the timestamp path offline.
    """
    settings = settings or load_settings()
    signer = load_signer(settings)

    # 1. Work out what the records are. Normally we read them straight back out
    #    of the document, so the manifest describes the document as it actually
    #    prints - not as some upstream system believes it prints.
    if records is None:
        records = extract_records(pdf_bytes)

    if timestamper is None:
        timestamper = build_timestamper(settings)

    # 2. Put the self-verifying cover page on the front, BEFORE sealing, so the
    #    seal covers it: the QR code and the record count cannot be swapped out
    #    without breaking the seal.
    cover_info = {"cover_page": False, "content_timestamp": None}
    timestamp_token = None
    if settings.cover_page and records:
        sealed_at, timestamp_token = content_timestamp(pdf_bytes, timestamper)
        cover = render_cover_page(
            verify_url=settings.verify_url,
            record_count=len(records),
            sealed_time=sealed_at,
            signer=_friendly_signer(signer),
            reference=(source or {}).get("case_ref", ""),
            demo_mode=not settings.is_production,
            timestamp_authority=_tsa_label(settings),
            logo_path=find_cover_logo(settings.cover_logo),
        )
        pdf_bytes = prepend_cover(cover, pdf_bytes)
        # Page numbers shifted, so re-read the records to keep the manifest
        # pointing at the pages a reader will actually turn to.
        records = extract_records(pdf_bytes)
        cover_info = {
            "cover_page": True,
            "content_timestamp": sealed_at.isoformat() if sealed_at else None,
        }

    try:
        manifest = build_manifest(
            records,
            include_previews=settings.manifest_previews,
            source=source,
        )
    except ManifestError as e:
        raise SealError(str(e)) from e

    # 3. Attach the manifest, then sign. Both happen in one incremental update,
    #    so the signature covers the manifest: altering the manifest to match a
    #    doctored record breaks the seal.
    timestamp_note = "disabled - no timestamp authority configured"
    timestamped = False

    try:
        sealed = _write_sealed(
            pdf_bytes, manifest, signer, timestamper, timestamp_token
        )
        if timestamper is not None:
            timestamped = True
            timestamp_note = f"timestamped by {getattr(timestamper, 'url', 'the configured authority')}"
    except Exception as e:
        if timestamper is None:
            raise SealError(f"Could not apply the seal: {e}") from e
        if settings.tsa_required:
            raise SealError(
                "The trusted timestamp could not be obtained and "
                "COMMCHECKER_TSA_REQUIRED is on, so the document was not "
                f"sealed. Timestamp authority: {settings.tsa_url}. "
                f"Underlying error: {e}"
            ) from e
        # Timestamping is optional here (the local demo may be offline), so
        # fall back to an untimestamped seal and say so plainly.
        sealed = _write_sealed(pdf_bytes, manifest, signer, None, timestamp_token)
        timestamp_note = (
            f"NOT timestamped - {settings.tsa_url} could not be reached ({e})"
        )

    info = {
        "records_sealed": len(records),
        "manifest_sha256": manifest["manifest_sha256"],
        "timestamped": timestamped,
        "timestamp_note": timestamp_note,
        "signing_mode": settings.mode,
        "signer_subject": signer.signing_cert.subject.human_friendly,
        **cover_info,
    }
    return sealed, info


def _friendly_signer(signer) -> str:
    """The signer's common name, for a human to read on the cover page."""
    try:
        subject = signer.signing_cert.subject
        return subject.native.get("common_name") or subject.human_friendly
    except Exception:
        return ""


def _tsa_label(settings: Settings) -> str:
    """A readable name for the timestamp authority, from its URL."""
    if not settings.tsa_url:
        return ""
    label = settings.tsa_url.split("//")[-1].split("/")[0]
    return label


def _write_sealed(
    pdf_bytes: bytes,
    manifest: dict,
    signer: signers.SimpleSigner,
    timestamper,
    timestamp_token: Optional[bytes] = None,
) -> bytes:
    """Embed the manifest and apply the signature in a single pass."""
    writer = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes))

    payload = manifest_bytes(manifest)
    embed.embed_file(
        writer,
        embed.FileSpec(
            file_spec_string=MANIFEST_FILENAME,
            file_name=MANIFEST_FILENAME,
            embedded_data=embed.EmbeddedFileObject.from_file_data(
                writer, data=payload, mime_type="application/json"
            ),
            description=(
                "CommLocker per-record hash manifest - one SHA-256 fingerprint "
                "per communication record."
            ),
        ),
    )

    if timestamp_token:
        # Attach the content timestamp so the time printed on the cover page
        # can be checked independently, without trusting the cover page.
        embed.embed_file(
            writer,
            embed.FileSpec(
                file_spec_string=TIMESTAMP_FILENAME,
                file_name=TIMESTAMP_FILENAME,
                embedded_data=embed.EmbeddedFileObject.from_file_data(
                    writer, data=timestamp_token,
                    mime_type="application/timestamp-reply",
                ),
                description=(
                    "RFC-3161 timestamp token over the records, as printed on "
                    "the cover page."
                ),
            ),
        )

    output = signers.sign_pdf(
        writer,
        PdfSignatureMetadata(
            field_name=SEAL_FIELD_NAME,
            reason=SEAL_REASON,
            # PAdES: the European/ETSI signature profile, which is what makes
            # this a long-lived document signature rather than a bare PKCS#7.
            subfilter=SigSeedSubFilter.PADES,
        ),
        signer=signer,
        timestamper=timestamper,
    )
    return output.getvalue()


# ---------------------------------------------------------------------------
# File-based convenience wrappers (the CLI uses these; the web service does not)
# ---------------------------------------------------------------------------
def seal(
    in_pdf: str,
    out_pdf: str,
    settings: Optional[Settings] = None,
    source: Optional[dict] = None,
    timestamper=None,
) -> dict:
    """Seal a PDF on disk. Returns the same info dict as seal_bytes."""
    with open(in_pdf, "rb") as f:
        data = f.read()
    sealed, info = seal_bytes(
        data, settings=settings, source=source, timestamper=timestamper
    )
    with open(out_pdf, "wb") as f:
        f.write(sealed)
    info["output"] = out_pdf
    return info
