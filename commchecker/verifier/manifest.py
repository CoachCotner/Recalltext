"""
The per-record hash manifest.

The digital seal answers "did anything change?". The manifest answers
"*what* changed?" - and that is the difference between "this document is
suspect" and "message 4 of 22, sent 11 Aug at 2:32pm, used to say X".

How it works
------------
1. Every record (one text message, one call log line) is printed on the page
   with a machine-readable header line:

       RECORD 0004 | 2025-08-11T14:32:00Z | INBOUND | +15550142
       Confirmed for tomorrow at 2.

2. At sealing time we read those records back out of the PDF, reduce each one
   to a canonical string, and take its SHA-256 fingerprint. The list of
   fingerprints is the manifest.

3. The manifest is attached to the PDF *before* the seal is applied, so the
   seal covers it. Editing the manifest breaks the seal.

4. At verification time we read the records out of the PDF again, recompute
   the fingerprints the same way, and compare. Any record whose fingerprint
   moved is named.

The canonical form is the contract. Both sides must produce byte-identical
strings for an unchanged record, so it is versioned: "commlocker-text/1".
"""
import hashlib
import io
import json
import re
import unicodedata
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

class ManifestError(Exception):
    """The document carries a manifest, but it is not a usable one."""


MANIFEST_FILENAME = "commlocker-manifest.json"
MANIFEST_SCHEMA = "commlocker.manifest/1"
CANONICALIZATION = "commlocker-text/1"
HASH_ALGORITHM = "sha256"
PREVIEW_CHARS = 140

# Matches the record header line, tolerating whatever spacing a PDF text
# extractor happens to produce.
RECORD_HEADER = re.compile(
    r"^\s*RECORD\s+(?P<id>\d{1,6})\s*\|"
    r"\s*(?P<sent>[^|]*?)\s*\|"
    r"\s*(?P<direction>[^|]*?)\s*\|"
    r"\s*(?P<party>.*?)\s*$"
)


@dataclass
class Record:
    """One communication record as it appears in the export."""

    id: str
    sent_utc: str
    direction: str
    party: str
    body: str
    page: int = 0

    def canonical(self) -> str:
        """
        The exact string that gets fingerprinted.

        Whitespace is normalised because PDF text extraction is allowed to
        differ in spacing without the content having changed; everything else
        is preserved exactly.
        """
        return "\n".join(
            [
                CANONICALIZATION,
                _norm(self.id),
                _norm(self.sent_utc),
                _norm(self.direction).upper(),
                _norm(self.party),
                _norm(self.body),
            ]
        )

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical().encode("utf-8")).hexdigest()

    def preview(self, limit: int = PREVIEW_CHARS) -> str:
        body = _norm(self.body)
        return body if len(body) <= limit else body[: limit - 1] + "…"


def _norm(text: str) -> str:
    """Unicode-normalise and collapse whitespace runs to single spaces."""
    if text is None:
        return ""
    text = unicodedata.normalize("NFC", str(text))
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Reading records out of a PDF
# ---------------------------------------------------------------------------
def extract_records(pdf_bytes: bytes) -> List[Record]:
    """
    Pull every RECORD block out of a PDF's text layer.

    The same function runs at sealing time and at verification time, which is
    what guarantees the two sides agree on what a record is.
    """
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    records: List[Record] = []

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            continue

        current: Optional[Record] = None
        body_lines: List[str] = []

        for line in text.splitlines():
            match = RECORD_HEADER.match(line)
            if match:
                if current is not None:
                    current.body = "\n".join(body_lines)
                    records.append(current)
                current = Record(
                    id=match.group("id"),
                    sent_utc=match.group("sent"),
                    direction=match.group("direction"),
                    party=match.group("party"),
                    body="",
                    page=page_number,
                )
                body_lines = []
            elif current is not None:
                body_lines.append(line)

        if current is not None:
            current.body = "\n".join(body_lines)
            records.append(current)

    return records


# ---------------------------------------------------------------------------
# Building and reading the manifest
# ---------------------------------------------------------------------------
def build_manifest(
    records: List[Record],
    include_previews: bool = True,
    source: Optional[dict] = None,
) -> dict:
    """Turn a list of records into the manifest that gets sealed into the PDF."""
    # Records are matched by number at verification time, so a repeated number
    # would leave one record permanently unchecked while the report claimed
    # full coverage. Refuse to seal an export that cannot be verified.
    seen = set()
    duplicates = sorted({r.id for r in records if r.id in seen or seen.add(r.id)})
    if duplicates:
        raise ManifestError(
            "cannot seal this export: record number(s) "
            + ", ".join(duplicates)
            + " appear more than once. Record numbering must be unique."
        )

    entries = []
    for record in records:
        entry = {
            "id": record.id,
            "page": record.page,
            "sent_utc": _norm(record.sent_utc),
            "direction": _norm(record.direction).upper(),
            "party": _norm(record.party),
            HASH_ALGORITHM: record.fingerprint(),
        }
        if include_previews:
            entry["preview"] = record.preview()
        entries.append(entry)

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "canonicalization": CANONICALIZATION,
        "hash_algorithm": HASH_ALGORITHM,
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "record_count": len(entries),
        "source": source or {},
        "records": entries,
    }
    manifest["manifest_sha256"] = manifest_digest(manifest)
    return manifest


def manifest_digest(manifest: dict) -> str:
    """
    A single fingerprint over the whole record list.

    Covers order and membership, so deleting a record or shuffling the list
    changes this value even when every surviving record is untouched.
    """
    joined = "\n".join(
        f"{e.get('id')}:{e.get(HASH_ALGORITHM)}"
        for e in manifest.get("records", [])
        if isinstance(e, dict)
    )
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def manifest_bytes(manifest: dict) -> bytes:
    """Serialise deterministically - same manifest, same bytes, every time."""
    return json.dumps(
        manifest, indent=2, sort_keys=True, ensure_ascii=False
    ).encode("utf-8")


def read_manifest(pdf_bytes: bytes) -> Optional[dict]:
    """
    Read the manifest back out of a PDF attachment.

    Returns None when the PDF carries no manifest, which is itself a finding:
    a genuine CommLocker export always has one.
    """
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        attachments = reader.attachments
    except Exception:
        return None

    payloads = attachments.get(MANIFEST_FILENAME) if attachments else None
    if not payloads:
        return None

    raw = payloads[0] if isinstance(payloads, list) else payloads
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise ManifestError(f"the attached manifest is not readable JSON: {e}")

    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest) -> None:
    """
    Check the manifest's shape before anything trusts it.

    The manifest arrives inside an uploaded file, so it is attacker-controlled
    until proven otherwise. Everything downstream indexes into it; without this
    a hand-crafted attachment turns a verification into a server crash.
    """
    if not isinstance(manifest, dict):
        raise ManifestError(
            f"the manifest should be a JSON object, found "
            f"{type(manifest).__name__}"
        )

    records = manifest.get("records")
    if records is None:
        raise ManifestError("the manifest lists no records")
    if not isinstance(records, list):
        raise ManifestError(
            f"the manifest's record list should be a list, found "
            f"{type(records).__name__}"
        )

    seen = set()
    for index, entry in enumerate(records):
        if not isinstance(entry, dict):
            raise ManifestError(
                f"manifest entry {index} should be an object, found "
                f"{type(entry).__name__}"
            )
        record_id = entry.get("id")
        if record_id is None:
            raise ManifestError(f"manifest entry {index} has no record id")
        if not isinstance(entry.get(HASH_ALGORITHM), str):
            raise ManifestError(
                f"manifest entry {record_id} has no {HASH_ALGORITHM} fingerprint"
            )
        # Records are matched by id, so a repeated id would silently hide one
        # record behind another.
        if str(record_id) in seen:
            raise ManifestError(
                f"record id {record_id} appears more than once - record "
                f"numbering must be unique"
            )
        seen.add(str(record_id))


# ---------------------------------------------------------------------------
# The comparison - this is what names the changed record
# ---------------------------------------------------------------------------
def compare_records(manifest: dict, records: List[Record]) -> dict:
    """
    Compare the manifest against the records currently in the document.

    Returns a structured result naming exactly which records changed, which
    were removed, and which were inserted.
    """
    expected: Dict[str, dict] = {
        str(e["id"]): e for e in manifest.get("records", []) if isinstance(e, dict)
    }

    # A repeated id in the document would let one record hide behind another,
    # so it is a finding in its own right rather than something to paper over.
    found: Dict[str, Record] = {}
    duplicate_ids: List[str] = []
    for record in records:
        if record.id in found:
            duplicate_ids.append(record.id)
        else:
            found[record.id] = record

    matched: List[str] = []
    changed: List[dict] = []
    missing: List[dict] = []
    added: List[dict] = []

    for record_id, entry in expected.items():
        record = found.get(record_id)
        if record is None:
            missing.append(
                {
                    "id": record_id,
                    "page": entry.get("page"),
                    "sent_utc": entry.get("sent_utc"),
                    "party": entry.get("party"),
                    "sealed_text": entry.get("preview"),
                    "what_happened": "This record was in the sealed document "
                    "and is no longer there - it was deleted.",
                }
            )
            continue

        actual_hash = record.fingerprint()
        if actual_hash == entry.get(HASH_ALGORITHM):
            matched.append(record_id)
        else:
            changed.append(
                {
                    "id": record_id,
                    "page": record.page,
                    "sent_utc": entry.get("sent_utc") or record.sent_utc,
                    "direction": entry.get("direction") or record.direction,
                    "party": entry.get("party") or record.party,
                    "sealed_text": entry.get("preview"),
                    "current_text": record.preview(),
                    "expected_sha256": entry.get(HASH_ALGORITHM),
                    "actual_sha256": actual_hash,
                    "what_happened": _describe_change(entry, record),
                }
            )

    for record_id, record in found.items():
        if record_id not in expected:
            added.append(
                {
                    "id": record_id,
                    "page": record.page,
                    "sent_utc": record.sent_utc,
                    "party": record.party,
                    "current_text": record.preview(),
                    "what_happened": "This record was not in the sealed "
                    "document - it was added afterwards.",
                }
            )

    manifest_intact = manifest.get("manifest_sha256") == manifest_digest(manifest)

    return {
        "duplicate_ids": sorted(set(duplicate_ids)),
        "record_count_sealed": len(expected),
        "record_count_found": len(found),
        "matched_count": len(matched),
        "matched": sorted(matched),
        "changed": sorted(changed, key=lambda c: c["id"]),
        "missing": sorted(missing, key=lambda c: c["id"]),
        "added": sorted(added, key=lambda c: c["id"]),
        "manifest_self_consistent": manifest_intact,
        "all_records_match": (
            not changed
            and not missing
            and not added
            and not duplicate_ids
            and manifest_intact
        ),
    }


def _describe_change(entry: dict, record: Record) -> str:
    """Say which part of the record moved, in words a non-technical reader gets."""
    parts = []
    if entry.get("sent_utc") and _norm(entry["sent_utc"]) != _norm(record.sent_utc):
        parts.append("the timestamp")
    if entry.get("party") and _norm(entry["party"]) != _norm(record.party):
        parts.append("the phone number")
    if entry.get("direction") and _norm(entry["direction"]).upper() != _norm(
        record.direction
    ).upper():
        parts.append("the direction (sent/received)")

    sealed_preview = entry.get("preview")
    if sealed_preview is not None and _norm(sealed_preview) != _norm(record.preview()):
        parts.append("the message text")

    if not parts:
        # The fingerprints differ but nothing we can show did. Either the
        # manifest stores no previews, or the change is past the preview
        # cut-off. Say which, rather than implying we looked and found nothing.
        if sealed_preview is None:
            return (
                "The content of this record no longer matches its sealed "
                "fingerprint. This manifest stores fingerprints only, so the "
                "original wording is not available for comparison."
            )
        return (
            "The content of this record no longer matches its sealed "
            "fingerprint. The change is beyond the stored preview."
        )
    return "Changed: " + ", ".join(parts) + "."


def summarise(comparison: dict) -> str:
    """One sentence a person can read off a screen."""
    changed = comparison["changed"]
    missing = comparison["missing"]
    added = comparison["added"]

    if comparison["all_records_match"]:
        n = comparison["record_count_found"]
        return f"All {n} records match their sealed fingerprints."

    bits = []
    if changed:
        ids = ", ".join(c["id"] for c in changed[:5])
        more = f" (+{len(changed) - 5} more)" if len(changed) > 5 else ""
        bits.append(
            f"{len(changed)} record{'s' if len(changed) != 1 else ''} changed: "
            f"{ids}{more}"
        )
    if missing:
        ids = ", ".join(m["id"] for m in missing[:5])
        bits.append(f"{len(missing)} deleted: {ids}")
    if added:
        ids = ", ".join(a["id"] for a in added[:5])
        bits.append(f"{len(added)} added: {ids}")
    if comparison.get("duplicate_ids"):
        ids = ", ".join(comparison["duplicate_ids"][:5])
        bits.append(f"duplicate record numbers: {ids}")
    if not comparison["manifest_self_consistent"]:
        bits.append("the manifest itself was altered")

    return "; ".join(bits) + "."


def records_to_dicts(records: List[Record]) -> List[dict]:
    return [asdict(r) for r in records]
