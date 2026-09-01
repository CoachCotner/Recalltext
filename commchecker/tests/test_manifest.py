"""The per-record manifest: canonical form, extraction, and the comparison."""
import pytest

from verifier.manifest import (
    Record,
    build_manifest,
    compare_records,
    extract_records,
    manifest_digest,
    read_manifest,
    summarise,
)


def make_record(body="Confirmed for tomorrow at 2.", **overrides):
    fields = dict(
        id="0003",
        sent_utc="2025-08-11T14:32:00Z",
        direction="INBOUND",
        party="+15550142",
        body=body,
        page=1,
    )
    fields.update(overrides)
    return Record(**fields)


class TestCanonicalForm:
    def test_same_content_same_fingerprint(self):
        assert make_record().fingerprint() == make_record().fingerprint()

    def test_whitespace_differences_do_not_change_the_fingerprint(self):
        """PDF extractors vary in spacing; that is not a content change."""
        spaced = make_record(body="Confirmed  for\n tomorrow   at 2.")
        plain = make_record(body="Confirmed for tomorrow at 2.")
        assert spaced.fingerprint() == plain.fingerprint()

    def test_content_change_changes_the_fingerprint(self):
        assert (
            make_record(body="...at 2.").fingerprint()
            != make_record(body="...at 5.").fingerprint()
        )

    @pytest.mark.parametrize(
        "field,value",
        [
            ("sent_utc", "2025-08-11T14:33:00Z"),
            ("party", "+15550199"),
            ("direction", "OUTBOUND"),
            ("id", "0004"),
        ],
    )
    def test_every_metadata_field_is_covered(self, field, value):
        assert make_record().fingerprint() != make_record(**{field: value}).fingerprint()

    def test_direction_case_is_not_significant(self):
        assert (
            make_record(direction="inbound").fingerprint()
            == make_record(direction="INBOUND").fingerprint()
        )


class TestExtraction:
    def test_reads_every_record_back_out_of_a_pdf(self, sample_pdf, records):
        extracted = extract_records(sample_pdf)
        assert len(extracted) == len(records)
        assert [r.id for r in extracted] == [r.id for r in records]

    def test_extracted_records_match_the_originals(self, sample_pdf, records):
        """The round trip through the PDF must not change any fingerprint."""
        extracted = {r.id: r for r in extract_records(sample_pdf)}
        for original in records:
            assert extracted[original.id].fingerprint() == original.fingerprint()

    def test_multi_line_bodies_survive_the_round_trip(self, sample_pdf):
        long_records = [r for r in extract_records(sample_pdf) if len(r.body) > 60]
        assert long_records, "the sample should contain a wrapped record"

    def test_metadata_is_parsed(self, sample_pdf):
        record = extract_records(sample_pdf)[2]
        assert record.id == "0003"
        assert record.direction == "INBOUND"
        assert record.party == "+15550142"
        assert record.page == 1


class TestComparison:
    def test_unchanged_records_all_match(self, records):
        manifest = build_manifest(records)
        result = compare_records(manifest, records)
        assert result["all_records_match"]
        assert result["matched_count"] == len(records)
        assert result["changed"] == []

    def test_names_the_changed_record(self, records):
        manifest = build_manifest(records)
        records[2].body = "Confirmed for tomorrow at 5."
        result = compare_records(manifest, records)

        assert not result["all_records_match"]
        assert len(result["changed"]) == 1
        changed = result["changed"][0]
        assert changed["id"] == "0003"
        assert changed["sealed_text"] == "Confirmed for tomorrow at 2."
        assert changed["current_text"] == "Confirmed for tomorrow at 5."
        assert changed["expected_sha256"] != changed["actual_sha256"]

    def test_only_the_changed_record_is_flagged(self, records):
        manifest = build_manifest(records)
        records[2].body = "something else"
        result = compare_records(manifest, records)
        assert result["matched_count"] == len(records) - 1

    def test_detects_a_deleted_record(self, records):
        manifest = build_manifest(records)
        removed = records.pop(1)
        result = compare_records(manifest, records)
        assert [m["id"] for m in result["missing"]] == [removed.id]
        assert not result["all_records_match"]

    def test_detects_an_inserted_record(self, records):
        manifest = build_manifest(records)
        records.append(make_record(id="9999", body="I never said this."))
        result = compare_records(manifest, records)
        assert [a["id"] for a in result["added"]] == ["9999"]
        assert not result["all_records_match"]

    def test_identifies_which_field_moved(self, records):
        manifest = build_manifest(records)
        records[2].sent_utc = "2025-08-11T18:00:00Z"
        result = compare_records(manifest, records)
        assert "timestamp" in result["changed"][0]["what_happened"]

    def test_summary_names_the_record(self, records):
        manifest = build_manifest(records)
        records[2].body = "changed"
        assert "0003" in summarise(compare_records(manifest, records))

    def test_manifest_digest_covers_membership(self, records):
        manifest = build_manifest(records)
        assert manifest["manifest_sha256"] == manifest_digest(manifest)
        manifest["records"].pop()
        assert manifest["manifest_sha256"] != manifest_digest(manifest)


class TestPreviews:
    def test_previews_can_be_switched_off(self, records):
        manifest = build_manifest(records, include_previews=False)
        assert all("preview" not in e for e in manifest["records"])

    def test_hash_only_manifest_still_detects_change(self, records):
        manifest = build_manifest(records, include_previews=False)
        records[2].body = "changed"
        result = compare_records(manifest, records)
        assert [c["id"] for c in result["changed"]] == ["0003"]


def test_no_manifest_in_an_unsealed_pdf(sample_pdf):
    assert read_manifest(sample_pdf) is None


class TestChangeDescriptions:
    def test_a_hash_only_manifest_says_the_wording_is_unavailable(self, records):
        """Do not imply we compared text when no text was stored."""
        manifest = build_manifest(records, include_previews=False)
        records[2].body = "completely different wording"
        description = compare_records(manifest, records)["changed"][0][
            "what_happened"
        ]
        assert "fingerprints only" in description

    def test_a_preview_manifest_names_the_message_text(self, records):
        manifest = build_manifest(records)
        records[2].body = "completely different wording"
        description = compare_records(manifest, records)["changed"][0][
            "what_happened"
        ]
        assert "message text" in description
