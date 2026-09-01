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
    ManifestError,
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
        "severity": SEVERITY_ALERT,
        "headline": "FAIL",
        "failure_kind": None,
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
        report["failure_kind"] = "unreadable"
        report["message"] = "This is not a readable PDF."
        return report

    if not signatures:
        add("Carries a CommLocker seal", False, "no digital signature found")
        report["failure_kind"] = "no_seal"
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
        report["failure_kind"] = "malformed_seal"
        report["message"] = "The seal on this file is malformed and cannot be checked."
        _attach_record_findings(report, pdf_bytes, add, sealed=True)
        return report

    add(
        "File unchanged since sealing",
        status.intact,
        "every sealed byte is exactly as it was"
        if status.intact
        # Careful here: a broken seal does NOT mean the words changed. Saving a
        # PDF rewrites the whole file. Saying "altered" would contradict the
        # re-save verdict and send a broker escalating a routine problem.
        else "the file's bytes are not the bytes that were sealed - this "
        "happens when a PDF is re-saved, and also when content is changed. "
        "The record check below is what tells the two apart",
    )
    add(
        "Seal is cryptographically well-formed",
        status.valid,
        "the signature math is sound"
        if status.valid
        else "the signature itself is malformed or forged",
    )

    # Coverage: content appended after the seal is not covered by it. This is
    # only measurable while the sealed bytes still hold - a rewritten file
    # reports odd coverage as a side effect of the rewrite, not an append, and
    # reporting that as "content was added" would be plainly wrong.
    coverage_name = getattr(status.coverage, "name", str(status.coverage))
    covers_whole_file = coverage_name == "ENTIRE_FILE"
    if not status.intact:
        add(
            "Seal covers the whole document",
            None,
            "could not be evaluated - the file was rewritten, so how much of "
            "it the seal covered can no longer be measured",
        )
    else:
        add(
            "Seal covers the whole document",
            covers_whole_file,
            "nothing was appended after sealing"
            if covers_whole_file
            else "content was added to this file after the seal was applied",
        )

    # Trust: only judge it when we actually have anchors to judge against.
    anchor_kind = trust_description["anchor_kind"]
    if not status.intact:
        # The sealed bytes changed, so nothing can be concluded about the
        # signer. Reporting a red cross here would read as "forged" on what is
        # usually just a re-saved copy.
        add(
            "Sealed by a trusted certificate",
            None,
            "could not be evaluated - the file no longer matches its seal, so "
            "the signer cannot be confirmed either way",
        )
    elif anchor_kind == "configured":
        add(
            "Sealed by a trusted certificate",
            status.trusted,
            f"signer chains to a configured trust anchor "
            f"({trust_description['root_count']} root(s) loaded)"
            if status.trusted
            else "the signer's certificate does not chain to any trusted root",
        )
    elif anchor_kind == "demo-self-trust":
        # The demo certificate is the only anchor here, so this check still
        # means something: it catches a document sealed by somebody else's key.
        # What it cannot do is prove real-world trust, which the wording says.
        add(
            "Sealed by a trusted certificate",
            status.trusted,
            "sealed by this installation's own demo certificate - DEMO ONLY, "
            "this proves nothing about real-world trust"
            if status.trusted
            else "NOT sealed by this installation's demo certificate - the "
            "signer is unknown, so this file did not come from here",
        )
        report["warnings"].append(
            "Running in demo mode with a self-signed certificate. This proves "
            "the file is unchanged, but not who sealed it. Configure a real "
            "CA certificate before relying on identity."
        )
    else:
        # Nothing to judge against. We cannot certify the signer, and saying
        # PASS here would claim more than was actually checked.
        add(
            "Sealed by a trusted certificate",
            False,
            "no trust roots are configured, so the signer could not be "
            "verified at all (set COMMCHECKER_TRUST_SYSTEM_ROOTS=1, or "
            "COMMCHECKER_TRUST_ROOTS)",
        )
        report["warnings"].append(
            "No trust roots are configured, so this file's origin cannot be "
            "checked. Integrity was still verified."
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
    try:
        manifest = read_manifest(pdf_bytes)
    except ManifestError as e:
        # The document carries something claiming to be a manifest but it is
        # not usable. That is a finding, not a crash.
        report["records"] = {
            "manifest_present": False,
            "manifest_error": str(e),
            "summary": f"This document's per-record manifest is unusable: {e}",
        }
        add("Per-record manifest is readable", False, str(e))
        return

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


# How a failure should be presented. A broker's first FAIL is almost always the
# innocent one - somebody opened the PDF and re-saved it - and a tool that
# shouts "TAMPERED" at that will be ignored by the third time it happens. So we
# separate what we actually observed from how alarmed to be about it.
SEVERITY_NONE = "none"      # PASS
SEVERITY_NOTICE = "notice"  # something to fix, nobody did anything wrong
SEVERITY_ALERT = "alert"    # escalate


def _decide_verdict(report: dict, status, anchor_kind: str) -> None:
    """
    Turn the checks into one word, and one sentence explaining it.

    PASS means every question this tool asked came back clean. A question it
    could not answer is not a pass - "we could not check who sealed this" must
    never be reported as "this is fine", because the person reading the banner
    takes a green PASS as the whole answer.
    """
    records = report["records"]
    integrity_ok = bool(status.intact) and bool(status.valid)
    coverage_ok = report["seal"].get("coverage") == "ENTIRE_FILE"

    # Trust always counts. With no anchors configured, status.trusted is False
    # and the verdict says so rather than quietly waving the document through.
    trust_ok = bool(status.trusted)

    # A timestamp that is present but broken is evidence of tampering. It lives
    # in the part of the signature the seal does not cover, so nothing else
    # here would catch it.
    timestamp = report.get("timestamp") or {}
    timestamp_ok = not (timestamp.get("present") and not timestamp.get("intact"))

    records_ok = True
    if records.get("manifest_present"):
        records_ok = bool(records.get("all_records_match"))
    elif records.get("manifest_error"):
        records_ok = False

    if integrity_ok and coverage_ok and trust_ok and timestamp_ok and records_ok:
        report["verdict"] = "PASS"
        report["severity"] = SEVERITY_NONE
        report["headline"] = "PASS"
        report["failure_kind"] = None
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
    kind, severity, headline, message = _classify_failure(
        report, status, anchor_kind, integrity_ok, coverage_ok, trust_ok,
        timestamp_ok, records_ok,
    )
    report["failure_kind"] = kind
    report["severity"] = severity
    report["headline"] = headline
    report["message"] = message


def _classify_failure(
    report, status, anchor_kind, integrity_ok, coverage_ok, trust_ok,
    timestamp_ok, records_ok,
):
    """
    Work out WHICH kind of failure this is, most serious first.

    The distinction that matters operationally is between a document whose
    content was changed and one whose content is intact but whose container was
    rewritten - a re-save. The per-record manifest is what separates them: if
    every record still matches its sealed fingerprint, the words on the page
    are the words that were sealed.

    Reading the underlying signals:

      intact=False                 the sealed bytes are not what they were.
                                   Re-saving a PDF does this without touching
                                   a single word, so on its own it proves
                                   nothing about the content.
      intact=True, coverage!=whole something was appended after the seal while
                                   leaving the sealed bytes alone. That is a
                                   deliberate act, not a side effect of saving.
    """
    records = report["records"]

    # 1. Content actually changed. The escalate case.
    if records.get("manifest_present") and not records_ok:
        return (
            "altered",
            SEVERITY_ALERT,
            "FAIL",
            "This record was changed after it was sealed - flag for review. "
            + records["summary"],
        )

    # 2. A manifest that is present but unusable. Saving a PDF does not produce
    #    malformed JSON, so this is not the innocent case.
    if records.get("manifest_error"):
        return (
            "manifest_unusable",
            SEVERITY_ALERT,
            "FAIL",
            "This document's per-record manifest is unusable, so its records "
            "could not be checked. Flag for review.",
        )

    # 3. Content appended after the seal, with the sealed bytes left intact.
    #    Only meaningful while the seal itself still holds - a rewritten file
    #    reports odd coverage as a side effect of the rewrite, not an append.
    if integrity_ok and not coverage_ok:
        return (
            "appended",
            SEVERITY_ALERT,
            "FAIL",
            "Content was ADDED to this file after it was sealed - flag for "
            "review.",
        )

    # 4. A broken timestamp means the seal itself was interfered with. Only
    #    readable while the sealed bytes still hold.
    if integrity_ok and not timestamp_ok:
        return (
            "broken_timestamp",
            SEVERITY_ALERT,
            "FAIL",
            "The trusted timestamp on this seal is BROKEN - the sealing time "
            "cannot be relied on. Flag for review.",
        )

    # 5. Sealed by someone we do not trust. Again only meaningful on an
    #    otherwise-intact seal: a rewritten file cannot vouch for its signer
    #    either, and that is a symptom of the rewrite, not a forged identity.
    if integrity_ok and not trust_ok:
        if anchor_kind == "none":
            return (
                "signer_unverifiable",
                SEVERITY_NOTICE,
                "CANNOT VERIFY",
                "The file is unchanged, but no trust roots are configured, so "
                "CommChecker cannot confirm who sealed it. This is a setup "
                "problem on this server, not a problem with the document.",
            )
        return (
            "untrusted_signer",
            SEVERITY_ALERT,
            "FAIL",
            "This file was NOT sealed by a trusted certificate - it did not "
            "come from where it claims to. Flag for review.",
        )

    # 6. The seal is broken, but every record still matches its fingerprint.
    #    Almost always somebody opened the PDF and saved it again, which
    #    rewrites the file and breaks the seal without touching the words.
    if not integrity_ok and records.get("manifest_present"):
        return (
            "resaved",
            SEVERITY_NOTICE,
            "RE-FILE",
            "This appears to be a re-saved copy. Re-file the original sealed "
            "export.",
        )

    # 7. The seal is broken and the fingerprints went with it, so the content
    #    could not be checked either way. Many PDF tools drop attachments on
    #    save, so this is usually the same innocent re-save - but we did not
    #    verify that, and the wording must not pretend we did.
    if not integrity_ok:
        return (
            "unverifiable",
            SEVERITY_NOTICE,
            "RE-FILE",
            "The seal is broken and this copy no longer carries its record "
            "fingerprints, so the content could not be checked. Re-file the "
            "original sealed export. If the original cannot be produced, flag "
            "for review.",
        )

    return (
        "unknown",
        SEVERITY_ALERT,
        "FAIL",
        "This record did not pass verification.",
    )


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
