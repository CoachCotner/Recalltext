"""
How a failure is reported.

This is a product decision, not a cosmetic one. A broker's first FAIL will
almost always be innocent - somebody opened the PDF and saved it again, which
rewrites the file and breaks the seal without changing a single word. If the
tool shouts "TAMPERED" at that, it will be ignored by the third time it
happens, and then it is worthless on the day it matters.

So the verifier separates what it observed from how alarmed to be:

  severity "notice"  something to fix, nobody did anything wrong
  severity "alert"   escalate
"""
import io

import pytest

from verifier import load_settings, seal_bytes, verify_bytes
from verifier.certs import make_demo_cert
from verifier.sample import render_records_pdf, sample_records


@pytest.fixture
def sealed(sample_pdf, settings):
    data, _ = seal_bytes(sample_pdf, settings)
    return data


def resave(pdf_bytes, drop_attachments=False):
    """
    Re-save a PDF the way a viewer application would.

    Rewrites the whole file structure while leaving every word intact - which
    is exactly what breaks the seal on an innocent document.
    """
    import pikepdf

    with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
        if drop_attachments:
            del pdf.Root.Names.EmbeddedFiles
        out = io.BytesIO()
        pdf.save(out)
    return out.getvalue()


class TestTheInnocentCase:
    """Re-saved: content intact, container rewritten."""

    @pytest.fixture
    def report(self, sealed, settings):
        return verify_bytes(resave(sealed), settings)

    def test_it_is_recognised_as_a_re_save(self, report):
        assert report["failure_kind"] == "resaved"

    def test_it_uses_the_agreed_wording(self, report):
        assert report["message"] == (
            "This appears to be a re-saved copy. Re-file the original sealed "
            "export."
        )

    def test_it_is_a_notice_not_an_alert(self, report):
        assert report["severity"] == "notice"

    def test_the_headline_asks_for_the_original_rather_than_shouting(self, report):
        assert report["headline"] == "RE-FILE"

    def test_it_does_not_accuse_anyone_of_changing_anything(self, report):
        assert "changed" not in report["message"].lower()
        assert "flag for review" not in report["message"].lower()

    def test_the_signer_check_is_not_marked_failed(self, report):
        """
        A rewritten file cannot vouch for its signer either. Showing that as a
        red cross would read as "forged" on an innocent document.
        """
        checks = {c["check"]: c["ok"] for c in report["checks"]}
        assert checks["Sealed by a trusted certificate"] is None

    def test_the_verdict_is_still_fail(self, report):
        """Softer wording, same outcome: this is not the original file."""
        assert report["verdict"] == "FAIL"


class TestTheInnocentCaseWithAttachmentsDropped:
    """Many PDF tools discard attachments on save, taking the manifest too."""

    @pytest.fixture
    def report(self, sealed, settings):
        return verify_bytes(resave(sealed, drop_attachments=True), settings)

    def test_it_is_reported_as_unverifiable(self, report):
        assert report["failure_kind"] == "unverifiable"

    def test_it_is_still_a_notice(self, report):
        assert report["severity"] == "notice"

    def test_it_does_not_claim_the_content_was_checked(self, report):
        """We could not check the records. The wording must not imply we did."""
        assert "could not be checked" in report["message"]

    def test_it_says_what_to_do_if_the_original_is_gone(self, report):
        assert "flag for review" in report["message"].lower()


class TestTheEscalateCase:
    """Content actually changed after sealing."""

    @pytest.fixture
    def report(self, sealed, settings):
        tampered = sealed.replace(b"tomorrow at 2.", b"tomorrow at 5.")
        assert tampered != sealed
        return verify_bytes(tampered, settings)

    def test_it_is_recognised_as_an_alteration(self, report):
        assert report["failure_kind"] == "altered"

    def test_it_uses_the_agreed_wording(self, report):
        assert report["message"].startswith(
            "This record was changed after it was sealed - flag for review."
        )

    def test_it_is_an_alert(self, report):
        assert report["severity"] == "alert"
        assert report["headline"] == "FAIL"

    def test_it_still_names_the_record(self, report):
        assert [c["id"] for c in report["records"]["changed"]] == ["0003"]

    def test_it_still_shows_the_before_and_after(self, report):
        changed = report["records"]["changed"][0]
        assert changed["sealed_text"] == "Confirmed for tomorrow at 2."
        assert changed["current_text"] == "Confirmed for tomorrow at 5."


class TestAlterationInsideAResave:
    """
    The case that decides whether the distinction is worth anything: somebody
    edits a record AND re-saves, so the file is rewritten too. The manifest has
    to see past the rewrite to the changed content.
    """

    def test_a_change_hidden_in_a_re_save_still_escalates(self, sealed, settings):
        tampered = sealed.replace(b"tomorrow at 2.", b"tomorrow at 5.")
        assert tampered != sealed
        report = verify_bytes(resave(tampered), settings)

        assert report["failure_kind"] == "altered"
        assert report["severity"] == "alert"
        assert [c["id"] for c in report["records"]["changed"]] == ["0003"]


class TestOtherFailuresStayAlerts:
    """Softening the innocent case must not soften anything else."""

    def test_a_forged_certificate_still_alerts(self, settings, tmp_path):
        attacker = tmp_path / "attacker.p12"
        make_demo_cert(str(attacker), "x")

        records = sample_records()
        records[4].body = "We reject the terms."
        forged_source = render_records_pdf(records, title="Export")

        attacker_settings = load_settings()
        attacker_settings.demo_p12_path = str(attacker)
        attacker_settings.demo_p12_password = "x"
        forged, _ = seal_bytes(forged_source, attacker_settings)

        report = verify_bytes(forged, settings)
        assert report["failure_kind"] == "untrusted_signer"
        assert report["severity"] == "alert"

    def test_appended_content_still_alerts(self, sealed, settings):
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import signers as pyhanko_signers
        from pyhanko.sign.signers import PdfSignatureMetadata

        from verifier.certs import load_signer

        writer = IncrementalPdfFileWriter(io.BytesIO(sealed))
        out = pyhanko_signers.sign_pdf(
            writer,
            PdfSignatureMetadata(field_name="Appended"),
            signer=load_signer(settings),
        )
        report = verify_bytes(out.getvalue(), settings)
        assert report["failure_kind"] == "appended"
        assert report["severity"] == "alert"

    def test_a_clean_document_carries_no_failure_kind(self, sealed, settings):
        report = verify_bytes(sealed, settings)
        assert report["verdict"] == "PASS"
        assert report["severity"] == "none"
        assert report["failure_kind"] is None


class TestTheChecklistAgreesWithTheHeadline:
    """
    A calm headline over a checklist that says "the file was altered" is worse
    than no headline at all - the broker reads the scary line and escalates
    anyway. Every row has to be consistent with the verdict above it.
    """

    @pytest.fixture
    def report(self, sealed, settings):
        return verify_bytes(resave(sealed), settings)

    def test_no_row_claims_the_file_was_altered(self, report):
        for check in report["checks"]:
            assert "was altered" not in check["detail"]

    def test_no_row_claims_content_was_added(self, report):
        for check in report["checks"]:
            assert "content was added" not in check["detail"].lower()

    def test_the_coverage_row_is_not_marked_failed(self, report):
        """A rewritten file's coverage cannot be measured, so it is unknown."""
        checks = {c["check"]: c["ok"] for c in report["checks"]}
        assert checks["Seal covers the whole document"] is None

    def test_the_integrity_row_points_at_the_record_check(self, report):
        checks = {c["check"]: c["detail"] for c in report["checks"]}
        assert "record check" in checks["File unchanged since sealing"]

    def test_a_genuinely_altered_file_still_reads_as_serious(
        self, sealed, settings
    ):
        tampered = sealed.replace(b"tomorrow at 2.", b"tomorrow at 5.")
        report = verify_bytes(tampered, settings)
        checks = {c["check"]: c["ok"] for c in report["checks"]}
        assert checks["Every record matches its sealed fingerprint"] is False
        assert report["severity"] == "alert"
