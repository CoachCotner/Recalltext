"""
Verification: "Computer #2".

Given a PDF, answer one question - has anything changed since it was sealed? -
and when the answer is no, say exactly which record moved.

Four layers of checking, in order:

  1. Is there a seal at all?
  2. Does the seal still cover the file byte-for-byte? (the integrity question)
  3. Was it sealed by a key we trust, and when? (the identity and time questions)
  4. Which specific records changed? (the manifest question)

Layer 4 runs even when layer 2 has already failed. That is the whole point:
a broken seal tells you the document is dirty, the manifest tells you where.
"""
import hashlib
import io
from typing import List, Optional

from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import validate_pdf_signature

from .certs import build_validation_context, describe_certificate, load_signer
from .config import ConfigError, Settings, load_settings
from .manifest import (
    compare_records,
    extract_records,
    read_manifest,
    summarise,
)


def verify_bytes(
    pdf_bytes: bytes,
    settings: Optional[Settings] = None,
    filename: str = "(uploaded file)",
) -> dict:
    """
    Verify a PDF held in memory. Never writes to disk.

    Always returns a report dict - it does not raise on a bad document, because
    "this is not a valid sealed record" is an answer, not an error.
    """
    settings = settings or load_settings()

    report = {
        "file": filename,
        "file_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "file_size_bytes": len(pdf_bytes),
        "mode": settings.mode,
        "verdict": "FAIL",
        "message": "",
        "checks": [],
        "warnings": [],
        "seal": {},
        "timestamp": {"present": False},
        "records": {"manifest_present": False},
    }

    def add(name: str, ok: Optional[bool], detail: str) -> None:
        """ok=None means 'could not be evaluated' - shown as a warning, not a fail."""
        report["checks"].append(
            {"check": name, "ok": bool(ok) if ok is not None else None, "detail": detail}
        )

    # -- Layer 1: is this a sealed PDF at all? ------------------------------
    try:
        reader = PdfFileReader(io.BytesIO(pdf_bytes))
        signatures = reader.embedded_signatures
    except Exception as e:
        add("Readable PDF", False, f"the file could not be opened as a PDF: {e}")
        report["message"] = "This is not a readable PDF."
        return report

    if not signatures:
        add("Carries a CommLocker seal", False, "no digital signature found")
        report["message"] = (
            "NOT a verifiable CommLocker record - there is no seal on this file."
        )
        # Even unsealed, report what records are visible. It is useful context.
        _attach_record_findings(report, pdf_bytes, add, sealed=False)
        return report

    add(
        "Carries a CommLocker seal",
        True,
        f"{len(signatures)} signature field(s) present",
    )

    # -- Layer 2 and 3: the signature itself --------------------------------
    fallback_cert = None
    if not settings.is_production:
        try:
            fallback_cert = load_signer(settings).signing_cert
        except ConfigError:
            fallback_cert = None

    # The signer context may self-trust the demo certificate; the timestamp
    # context never does - a timestamp authority stands on real roots or none.
    signer_vc, trust_description = build_validation_context(settings, fallback_cert)
    ts_vc, _ = build_validation_context(settings, fallback_cert=None)

    try:
        status = validate_pdf_signature(
            signatures[0],
            signer_validation_context=signer_vc,
            ts_validation_context=ts_vc,
        )
    except Exception as e:
        add("Seal could be checked", False, f"the seal could not be evaluated: {e}")
        report["message"] = "The seal on this file is malformed and cannot be checked."
        _attach_record_findings(report, pdf_bytes, add, sealed=True)
        return report

    add(
        "File unchanged since sealing",
        status.intact,
        "every sealed byte is exactly as it was"
        if status.intact
        else "the file was altered after it was sealed",
    )
    add(
        "Seal is cryptographically well-formed",
        status.valid,
        "the signature math is sound"
        if status.valid
        else "the signature itself is malformed or forged",
    )

    # Coverage: content appended after the seal is not covered by it.
    coverage_name = getattr(status.coverage, "name", str(status.coverage))
    covers_whole_file = coverage_name == "ENTIRE_FILE"
    add(
        "Seal covers the whole document",
        covers_whole_file,
        "nothing was appended after sealing"
        if covers_whole_file
        else f"content was added after the seal was applied ({coverage_name})",
    )

    # Trust: only judge it when we actually have anchors to judge against.
    anchor_kind = trust_description["anchor_kind"]
    if anchor_kind == "configured":
        add(
            "Sealed by a trusted certificate",
            status.trusted,
            f"signer chains to a configured trust anchor "
            f"({trust_description['root_count']} root(s) loaded)"
            if status.trusted
            else "the signer's certificate does not chain to any trusted root",
        )
    elif anchor_kind == "demo-self-trust":
        add(
            "Sealed by a trusted certificate",
            None,
            "DEMO MODE - the seal was checked against the demo certificate "
            "itself, which proves nothing about real-world trust",
        )
        report["warnings"].append(
            "Running in demo mode with a self-signed certificate. This proves "
            "the file is unchanged, but not who sealed it. Configure a real "
            "CA certificate before relying on identity."
        )
    else:
        add(
            "Sealed by a trusted certificate",
            None,
            "no trust roots configured, so the signer's identity could not be "
            "evaluated (set COMMCHECKER_TRUST_ROOTS or "
            "COMMCHECKER_TRUST_SYSTEM_ROOTS=1)",
        )
        report["warnings"].append(
            "No trust roots are configured, so this check could not judge who "
            "sealed the file - only that it is unchanged."
        )

    signer_cert = getattr(status, "signing_cert", None)
    report["seal"] = {
        "signer": describe_certificate(signer_cert) if signer_cert else {},
        "trust": trust_description,
        "claimed_signing_time": _iso(getattr(status, "signer_reported_dt", None)),
        "coverage": coverage_name,
    }

    # -- The RFC-3161 trusted timestamp -------------------------------------
    _attach_timestamp_findings(report, status, add)

    # -- Layer 4: which records changed? ------------------------------------
    _attach_record_findings(report, pdf_bytes, add, sealed=True)

    # -- The verdict --------------------------------------------------------
    _decide_verdict(report, status, anchor_kind)
    return report


def _attach_timestamp_findings(report: dict, status, add) -> None:
    """Report the trusted timestamp, if the seal carries one."""
    ts = getattr(status, "timestamp_validity", None)
    if ts is None:
        report["timestamp"] = {"present": False}
        add(
            "Carries a trusted timestamp",
            None,
            "this seal has no RFC-3161 timestamp, so the sealing time rests on "
            "the signer's own clock",
        )
        report["warnings"].append(
            "No trusted timestamp. The seal still proves the file is "
            "unchanged, but not when it was sealed."
        )
        return

    ts_time = getattr(ts, "timestamp", None)
    ts_cert = getattr(ts, "signing_cert", None)
    ts_trusted = bool(getattr(ts, "trusted", False))
    ts_intact = bool(getattr(ts, "intact", False)) and bool(getattr(ts, "valid", False))

    report["timestamp"] = {
        "present": True,
        "time_utc": _iso(ts_time),
        "intact": ts_intact,
        "trusted": ts_trusted,
        "authority": ts_cert.subject.human_friendly if ts_cert else "unknown",
    }

    when = _iso(ts_time) or "an unrecorded time"
    if ts_intact and ts_trusted:
        add(
            "Carries a trusted timestamp",
            True,
            f"an independent timestamp authority certifies this document "
            f"existed in this exact form at {when}",
        )
    elif ts_intact:
        add(
            "Carries a trusted timestamp",
            None,
            f"a timestamp records {when}, but the timestamp authority's "
            f"certificate could not be traced to a trusted root",
        )
        report["warnings"].append(
            "The timestamp is present and internally consistent, but its "
            "authority is not verifiable against the configured trust roots."
        )
    else:
        add(
            "Carries a trusted timestamp",
            False,
            "the timestamp on this seal is broken or was tampered with",
        )


def _attach_record_findings(report: dict, pdf_bytes: bytes, add, sealed: bool) -> None:
    """
    The per-record comparison.

    Runs even on a document whose seal has already failed - a broken seal is
    exactly when you most want to know which record was touched.
    """
    manifest = read_manifest(pdf_bytes)

    if manifest is None:
        report["records"] = {
            "manifest_present": False,
            "summary": "This document carries no per-record manifest, so "
            "record-level detail is not available.",
        }
        if sealed:
            add(
                "Carries a per-record manifest",
                None,
                "no manifest attached - the seal still proves the file is "
                "unchanged, but cannot name individual records",
            )
            report["warnings"].append(
                "No per-record manifest found. This document was sealed by an "
                "older version of CommLocker, or the manifest was stripped."
            )
        return

    try:
        records = extract_records(pdf_bytes)
    except Exception as e:
        report["records"] = {
            "manifest_present": True,
            "summary": f"The manifest was found but the document's records "
            f"could not be read back: {e}",
        }
        add("Every record matches its sealed fingerprint", False,
            f"records could not be read from the document: {e}")
        return

    comparison = compare_records(manifest, records)
    comparison["manifest_present"] = True
    comparison["summary"] = summarise(comparison)
    comparison["manifest_created_utc"] = manifest.get("created_utc")
    comparison["source"] = manifest.get("source", {})
    report["records"] = comparison

    add(
        "Carries a per-record manifest",
        True,
        f"{comparison['record_count_sealed']} record fingerprints sealed into "
        f"the document",
    )
    add(
        "Every record matches its sealed fingerprint",
        comparison["all_records_match"],
        comparison["summary"],
    )


def _decide_verdict(report: dict, status, anchor_kind: str) -> None:
    """Turn the checks into one word, and one sentence explaining it."""
    records = report["records"]
    integrity_ok = bool(status.intact) and bool(status.valid)
    coverage_ok = report["seal"].get("coverage") == "ENTIRE_FILE"

    # Trust only counts against the verdict when it was genuinely evaluated.
    trust_ok = True
    if anchor_kind == "configured":
        trust_ok = bool(status.trusted)

    records_ok = True
    if records.get("manifest_present"):
        records_ok = bool(records.get("all_records_match"))

    if integrity_ok and coverage_ok and trust_ok and records_ok:
        report["verdict"] = "PASS"
        count = records.get("record_count_found")
        if records.get("manifest_present") and count:
            report["message"] = (
                f"Unaltered since sealing. All {count} records match their "
                f"sealed fingerprints."
            )
        else:
            report["message"] = "Unaltered since it was sealed."
        return

    report["verdict"] = "FAIL"

    # Lead with the most specific thing we know.
    if records.get("manifest_present") and not records_ok:
        report["message"] = "Record was CHANGED after sealing - " + records["summary"]
    elif not integrity_ok:
        report["message"] = (
            "This file was CHANGED after it was sealed - flag for review."
        )
    elif not coverage_ok:
        report["message"] = (
            "Content was ADDED to this file after it was sealed - flag for review."
        )
    elif not trust_ok:
        report["message"] = (
            "The file is unchanged, but it was not sealed by a trusted "
            "certificate - treat its origin as unproven."
        )
    else:
        report["message"] = "This record did not pass verification."


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


# ---------------------------------------------------------------------------
# File-based convenience wrapper (the CLI uses this; the web service does not)
# ---------------------------------------------------------------------------
def verify(pdf_path: str, settings: Optional[Settings] = None) -> dict:
    """Verify a PDF on disk."""
    with open(pdf_path, "rb") as f:
        data = f.read()
    return verify_bytes(data, settings=settings, filename=pdf_path)
