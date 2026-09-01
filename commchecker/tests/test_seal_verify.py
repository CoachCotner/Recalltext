"""Sealing and verifying: the PASS/FAIL behaviour the whole tool rests on."""
import pytest

from verifier import read_manifest, seal_bytes, verify_bytes
from verifier.manifest import extract_records


@pytest.fixture
def sealed(sample_pdf, settings):
    data, _ = seal_bytes(sample_pdf, settings)
    return data


class TestSealing:
    def test_sealing_reports_what_it_did(self, sample_pdf, settings):
        _, info = seal_bytes(sample_pdf, settings)
        assert info["records_sealed"] == 6
        assert info["signing_mode"] == "demo"
        assert info["manifest_sha256"]

    def test_the_manifest_is_embedded_in_the_output(self, sealed):
        manifest = read_manifest(sealed)
        assert manifest is not None
        assert manifest["record_count"] == 6
        assert len(manifest["records"]) == 6

    def test_the_manifest_carries_a_fingerprint_per_record(self, sealed):
        manifest = read_manifest(sealed)
        fingerprints = {e["sha256"] for e in manifest["records"]}
        assert len(fingerprints) == 6, "each record needs its own fingerprint"

    def test_source_metadata_is_recorded(self, sample_pdf, settings):
        data, _ = seal_bytes(sample_pdf, settings, source={"case_ref": "412 Maple"})
        assert read_manifest(data)["source"]["case_ref"] == "412 Maple"

    def test_sealing_does_not_disturb_the_records(self, sealed, records):
        """Sealing must not change what the document says."""
        after = {r.id: r for r in extract_records(sealed)}
        for original in records:
            assert after[original.id].fingerprint() == original.fingerprint()


class TestCleanDocument:
    def test_an_untouched_sealed_record_passes(self, sealed, settings):
        report = verify_bytes(sealed, settings)
        assert report["verdict"] == "PASS"

    def test_every_record_matches(self, sealed, settings):
        report = verify_bytes(sealed, settings)
        assert report["records"]["all_records_match"]
        assert report["records"]["matched_count"] == 6

    def test_the_integrity_checks_are_green(self, sealed, settings):
        checks = {c["check"]: c["ok"] for c in verify_bytes(sealed, settings)["checks"]}
        assert checks["File unchanged since sealing"] is True
        assert checks["Seal is cryptographically well-formed"] is True
        assert checks["Seal covers the whole document"] is True
        assert checks["Every record matches its sealed fingerprint"] is True


class TestTamperedDocument:
    @pytest.fixture
    def tampered(self, sealed):
        changed = sealed.replace(b"tomorrow at 2.", b"tomorrow at 5.")
        assert changed != sealed, "the tamper fixture did not change anything"
        return changed

    def test_a_tampered_record_fails(self, tampered, settings):
        assert verify_bytes(tampered, settings)["verdict"] == "FAIL"

    def test_the_seal_reports_the_file_as_altered(self, tampered, settings):
        checks = {c["check"]: c["ok"] for c in verify_bytes(tampered, settings)["checks"]}
        assert checks["File unchanged since sealing"] is False

    def test_it_names_the_specific_record_that_changed(self, tampered, settings):
        """This is the feature: not 'something changed' but 'record 0003 changed'."""
        report = verify_bytes(tampered, settings)
        changed = report["records"]["changed"]
        assert len(changed) == 1
        assert changed[0]["id"] == "0003"

    def test_it_shows_the_before_and_after_text(self, tampered, settings):
        changed = verify_bytes(tampered, settings)["records"]["changed"][0]
        assert changed["sealed_text"] == "Confirmed for tomorrow at 2."
        assert changed["current_text"] == "Confirmed for tomorrow at 5."

    def test_it_reports_the_page(self, tampered, settings):
        assert verify_bytes(tampered, settings)["records"]["changed"][0]["page"] == 1

    def test_the_other_records_are_not_flagged(self, tampered, settings):
        report = verify_bytes(tampered, settings)
        assert report["records"]["matched_count"] == 5
        assert report["records"]["missing"] == []
        assert report["records"]["added"] == []

    def test_the_headline_message_names_the_record(self, tampered, settings):
        assert "0003" in verify_bytes(tampered, settings)["message"]

    def test_a_single_byte_change_is_enough(self, sealed, settings):
        flipped = bytearray(sealed)
        # Flip a byte inside the page content, well past the PDF header.
        flipped[len(flipped) // 2] ^= 0x01
        assert verify_bytes(bytes(flipped), settings)["verdict"] == "FAIL"


class TestDocumentsThatAreNotSealedRecords:
    def test_an_unsigned_pdf_fails(self, sample_pdf, settings):
        report = verify_bytes(sample_pdf, settings)
        assert report["verdict"] == "FAIL"
        assert "no seal" in report["message"].lower()

    def test_a_non_pdf_fails_cleanly(self, settings):
        report = verify_bytes(b"this is not a PDF at all", settings)
        assert report["verdict"] == "FAIL"
        assert "not a readable pdf" in report["message"].lower()

    def test_an_empty_file_fails_cleanly(self, settings):
        assert verify_bytes(b"", settings)["verdict"] == "FAIL"

    def test_verification_never_raises_on_junk(self, settings):
        """A bad document is an answer, not a crash."""
        for junk in (b"%PDF-1.7\nbroken", b"\x00" * 500, b"%PDF-"):
            assert verify_bytes(junk, settings)["verdict"] == "FAIL"


class TestManifestTampering:
    def test_removing_the_manifest_breaks_the_seal(self, sealed, settings):
        """
        The manifest is attached before signing, so the seal covers it.

        An attacker who strips the manifest to disable record-level checking
        cannot do so without breaking the seal - which is the point.
        """
        import io

        import pikepdf

        with pikepdf.open(io.BytesIO(sealed)) as pdf:
            del pdf.Root.Names.EmbeddedFiles
            out = io.BytesIO()
            pdf.save(out)
        stripped = out.getvalue()

        assert read_manifest(stripped) is None, "the manifest should be gone"
        assert verify_bytes(stripped, settings)["verdict"] == "FAIL"

    def test_editing_the_manifest_breaks_the_seal(self, sealed, settings):
        """
        Doctoring a record and rewriting its fingerprint to match does not
        work either: rewriting the manifest is itself a change to the document.
        """
        import io
        import json

        import pikepdf

        with pikepdf.open(io.BytesIO(sealed)) as pdf:
            spec = pdf.Root.Names.EmbeddedFiles.Names[1]
            raw = bytes(spec.EF.F.read_bytes())
            manifest = json.loads(raw)
            manifest["records"][2]["sha256"] = "0" * 64
            spec.EF.F.write(json.dumps(manifest, indent=2).encode())
            out = io.BytesIO()
            pdf.save(out)
        doctored = out.getvalue()

        assert verify_bytes(doctored, settings)["verdict"] == "FAIL"

    def test_appending_content_after_the_seal_is_caught(self, sealed, settings):
        report = verify_bytes(sealed + b"\n% appended\n", settings)
        assert report["verdict"] == "FAIL"


class TestDocumentSealedWithoutAManifest:
    """
    Older CommLocker exports carry a seal but no manifest.

    They still verify - the seal alone answers "did anything change?" - but the
    report says plainly that record-level detail is unavailable, so nobody
    reads a bare PASS as more than it is.
    """

    @pytest.fixture
    def sealed_no_records(self, settings):
        """A sealed PDF whose pages carry no RECORD headers at all."""
        from verifier.sample import render_records_pdf

        plain = render_records_pdf([], title="Export with no records")
        data, _ = seal_bytes(plain, settings)
        return data

    def test_it_still_verifies(self, sealed_no_records, settings):
        assert verify_bytes(sealed_no_records, settings)["verdict"] == "PASS"

    def test_it_reports_zero_records_rather_than_claiming_detail(
        self, sealed_no_records, settings
    ):
        report = verify_bytes(sealed_no_records, settings)
        assert report["records"]["record_count_sealed"] == 0


class TestReportShape:
    """The web UI depends on these fields being present."""

    def test_report_has_the_fields_the_ui_renders(self, sealed, settings):
        report = verify_bytes(sealed, settings, filename="x.pdf")
        for key in (
            "file", "file_sha256", "verdict", "message", "checks",
            "warnings", "seal", "timestamp", "records", "mode",
        ):
            assert key in report, f"missing report field: {key}"

    def test_every_check_is_renderable(self, sealed, settings):
        for check in verify_bytes(sealed, settings)["checks"]:
            assert set(check) == {"check", "ok", "detail"}
            assert check["ok"] in (True, False, None)

    def test_the_file_hash_is_reported(self, sealed, settings):
        assert len(verify_bytes(sealed, settings)["file_sha256"]) == 64


class TestReSigningAttacks:
    """
    An attacker who cannot forge the seal may try to work around it: append
    their own signature to make the document look freshly signed, or doctor a
    record and re-sign to cover their tracks.
    """

    @pytest.fixture
    def attacker(self, tmp_path):
        from pyhanko.sign import signers as pyhanko_signers

        from verifier.certs import make_demo_cert

        path = tmp_path / "attacker.p12"
        make_demo_cert(str(path), "x")
        return pyhanko_signers.SimpleSigner.load_pkcs12(str(path), passphrase=b"x")

    @staticmethod
    def _append_signature(pdf_bytes, signer):
        import io

        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import signers as pyhanko_signers
        from pyhanko.sign.signers import PdfSignatureMetadata

        writer = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes))
        out = pyhanko_signers.sign_pdf(
            writer, PdfSignatureMetadata(field_name="AttackerSig"), signer=signer
        )
        return out.getvalue()

    def test_appending_another_signature_does_not_pass(
        self, sealed, settings, attacker
    ):
        """
        The appended signature is valid and the original seal is untouched, so
        only the coverage check stands between this and a false green light.
        """
        doubled = self._append_signature(sealed, attacker)
        report = verify_bytes(doubled, settings)

        assert report["verdict"] == "FAIL"
        checks = {c["check"]: c["ok"] for c in report["checks"]}
        assert checks["Seal covers the whole document"] is False

    def test_doctoring_then_re_signing_still_names_the_record(
        self, sealed, settings, attacker
    ):
        tampered = sealed.replace(b"tomorrow at 2.", b"tomorrow at 5.")
        re_signed = self._append_signature(tampered, attacker)

        report = verify_bytes(re_signed, settings)
        assert report["verdict"] == "FAIL"
        assert [c["id"] for c in report["records"]["changed"]] == ["0003"]


class TestMultiPageExports:
    """A real transaction thread runs to many pages, not one."""

    @pytest.fixture
    def long_thread(self):
        from verifier.manifest import Record
        from verifier.sample import render_records_pdf

        records = [
            Record(
                id=f"{i:04d}",
                sent_utc=f"2025-08-{(i % 28) + 1:02d}T09:{i % 60:02d}:00Z",
                direction="INBOUND" if i % 2 else "OUTBOUND",
                party="+15550142",
                body=f"Message number {i} about the closing schedule and the "
                f"appraisal contingency.",
            )
            for i in range(1, 61)
        ]
        return render_records_pdf(records, title="Long thread")

    def test_records_are_sealed_across_every_page(self, long_thread, settings):
        from verifier import read_manifest

        sealed, info = seal_bytes(long_thread, settings)
        assert info["records_sealed"] == 60

        pages = {e["page"] for e in read_manifest(sealed)["records"]}
        assert len(pages) > 1, "this fixture should span several pages"

    def test_a_clean_multi_page_export_passes(self, long_thread, settings):
        sealed, _ = seal_bytes(long_thread, settings)
        report = verify_bytes(sealed, settings)
        assert report["verdict"] == "PASS"
        assert report["records"]["record_count_found"] == 60

    def test_a_change_on_a_later_page_is_pinned_to_that_page(
        self, long_thread, settings
    ):
        sealed, _ = seal_bytes(long_thread, settings)
        tampered = sealed.replace(
            b"Message number 47 about", b"Message number 00 about"
        )
        assert tampered != sealed

        changed = verify_bytes(tampered, settings)["records"]["changed"]
        assert len(changed) == 1
        assert changed[0]["id"] == "0047"
        assert changed[0]["page"] > 1
