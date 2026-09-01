"""
The self-verifying cover page.

The point of the cover page is that the document proves itself wherever it
goes - Paperless Pipeline, Dotloop, an email attachment, a printout - without
the receiving system needing to know anything about CommChecker.
"""
import io

import pytest
from pypdf import PdfReader

from verifier import load_settings, read_manifest, seal_bytes, verify_bytes
from verifier.coverpage import (
    TIMESTAMP_FILENAME,
    content_timestamp,
    prepend_cover,
    render_cover_page,
)
from verifier.manifest import extract_records


def page_text(pdf_bytes, index=0):
    return PdfReader(io.BytesIO(pdf_bytes)).pages[index].extract_text() or ""


class TestTheCoverPageIsAdded:
    def test_sealing_adds_a_cover_page(self, sample_pdf, settings):
        before = len(PdfReader(io.BytesIO(sample_pdf)).pages)
        sealed, info = seal_bytes(sample_pdf, settings)
        assert info["cover_page"] is True
        assert len(PdfReader(io.BytesIO(sealed)).pages) == before + 1

    def test_the_cover_page_comes_first(self, sample_pdf, settings):
        sealed, _ = seal_bytes(sample_pdf, settings)
        assert "SEALED RECORD" in page_text(sealed, 0)

    def test_it_can_be_switched_off(self, sample_pdf, settings):
        settings.cover_page = False
        sealed, info = seal_bytes(sample_pdf, settings)
        assert info["cover_page"] is False
        assert "SEALED RECORD" not in page_text(sealed, 0)


class TestWhatTheCoverPageSays:
    @pytest.fixture
    def sealed(self, sample_pdf, settings):
        settings.verify_url = "https://verify.example.test"
        data, _ = seal_bytes(
            sample_pdf, settings, source={"case_ref": "412 Maple Street"}
        )
        return data

    def test_it_shows_the_record_count(self, sealed):
        assert "6" in page_text(sealed, 0)

    def test_it_shows_the_verify_link_as_readable_text(self, sealed):
        """Not everyone scans a QR code; the link has to be printed too."""
        assert "https://verify.example.test" in page_text(sealed, 0)

    def test_it_shows_the_reference(self, sealed):
        assert "412 Maple Street" in page_text(sealed, 0)

    def test_it_explains_all_three_outcomes(self, sealed):
        """A broker reading this should know what to do with any answer."""
        text = page_text(sealed, 0)
        for outcome in ("PASS", "RE-FILE", "FAIL"):
            assert outcome in text

    def test_it_marks_demo_seals_as_demo(self, sealed):
        assert "DEMO" in page_text(sealed, 0)


class TestTheVerifyUrlIsOneConfigValue:
    def test_the_url_comes_from_configuration(
        self, sample_pdf, clean_env, monkeypatch
    ):
        from verifier.certs import ensure_demo_cert

        monkeypatch.setenv("COMMCHECKER_VERIFY_URL", "https://check.mybrand.com")
        settings = load_settings()
        ensure_demo_cert(settings)

        sealed, _ = seal_bytes(sample_pdf, settings)
        assert "https://check.mybrand.com" in page_text(sealed, 0)

    def test_there_is_a_placeholder_until_it_is_deployed(self, clean_env):
        assert load_settings().verify_url.startswith("https://")


class TestTheCoverPageIsSealedToo:
    """
    The cover page carries the QR code and the record count, so it is added
    before signing. Swapping it for one pointing at a different site has to
    break the seal.
    """

    def test_editing_the_cover_page_breaks_the_seal(self, sample_pdf, settings):
        settings.verify_url = "https://verify.example.test"
        sealed, _ = seal_bytes(sample_pdf, settings)

        redirected = sealed.replace(
            b"https://verify.example.test", b"https://evil.example.test"
        )
        assert redirected != sealed, "the fixture did not change anything"
        assert verify_bytes(redirected, settings)["verdict"] == "FAIL"


class TestRecordPagesAccountForTheCover:
    def test_records_are_reported_on_the_page_they_print_on(
        self, sample_pdf, settings
    ):
        sealed, _ = seal_bytes(sample_pdf, settings)
        manifest = read_manifest(sealed)
        assert {e["page"] for e in manifest["records"]} == {2}

    def test_extraction_still_finds_every_record(self, sample_pdf, settings):
        sealed, _ = seal_bytes(sample_pdf, settings)
        assert len(extract_records(sealed)) == 6


class TestTheTimestampOnTheCover:
    def test_the_time_is_the_authority_s_and_the_token_is_attached(
        self, sample_pdf, settings, local_tsa
    ):
        """
        The printed time has to be independently checkable, so the RFC-3161
        token it came from travels with the document.
        """
        timestamper, _ = local_tsa
        sealed, info = seal_bytes(sample_pdf, settings, timestamper=timestamper)

        assert info["content_timestamp"] is not None
        attachments = PdfReader(io.BytesIO(sealed)).attachments
        assert TIMESTAMP_FILENAME in attachments

    def test_without_a_timestamp_the_cover_says_so(self, sample_pdf, settings):
        """It must not print a time it cannot stand behind."""
        sealed, info = seal_bytes(sample_pdf, settings)
        assert info["content_timestamp"] is None
        assert "no trusted timestamp" in page_text(sealed, 0)

    def test_no_timestamper_means_no_timestamp(self):
        assert content_timestamp(b"anything", None) == (None, None)

    def test_an_unreachable_authority_does_not_block_sealing(self, sample_pdf, settings):
        class Broken:
            url = "http://tsa.example.invalid"

            async def async_timestamp(self, *a, **k):
                raise IOError("unreachable")

        assert content_timestamp(b"x", Broken()) == (None, None)


class TestRenderingDirectly:
    def test_a_cover_page_renders_without_optional_details(self):
        """Reference, signer and timestamp are all optional."""
        pdf = render_cover_page(verify_url="https://x.test", record_count=0)
        assert pdf.startswith(b"%PDF")

    def test_prepending_preserves_the_original_pages(self, sample_pdf):
        cover = render_cover_page(verify_url="https://x.test", record_count=6)
        merged = prepend_cover(cover, sample_pdf)
        assert len(PdfReader(io.BytesIO(merged)).pages) == 2

    def test_prepending_leaves_the_text_layer_readable(self, sample_pdf):
        """The tamper demo depends on the text staying uncompressed."""
        cover = render_cover_page(verify_url="https://x.test", record_count=6)
        merged = prepend_cover(cover, sample_pdf)
        assert b"tomorrow at 2." in merged


class TestTheCommLockerLogoOnTheCover:
    """
    The cover page is the CommLocker product's page - CommLocker seals the
    record, CommChecker checks it - so it carries the CommLocker mark.

    Logo files are placed exactly as supplied. Nothing here recolours, traces
    or regenerates artwork, and a missing brand file must never stop a document
    being sealed.
    """

    @pytest.fixture
    def png_logo(self, tmp_path):
        from PIL import Image

        path = tmp_path / "CommLocker_logo_transparent.png"
        Image.new("RGBA", (800, 200), (197, 98, 48, 255)).save(path)
        return str(path)

    @pytest.fixture
    def svg_logo(self, tmp_path):
        path = tmp_path / "CommLocker_logo_POP.svg"
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="100">'
            '<rect width="400" height="100" fill="#C56230"/></svg>'
        )
        return str(path)

    def test_a_png_logo_is_placed(self, png_logo):
        with_logo = render_cover_page(
            verify_url="https://x.test", record_count=6, logo_path=png_logo
        )
        without = render_cover_page(verify_url="https://x.test", record_count=6)
        assert len(with_logo) > len(without)

    def test_an_svg_logo_is_placed_as_vector(self, svg_logo):
        """Vector stays crisp at any print size, so SVG is preferred."""
        with_logo = render_cover_page(
            verify_url="https://x.test", record_count=6, logo_path=svg_logo
        )
        without = render_cover_page(verify_url="https://x.test", record_count=6)
        assert len(with_logo) > len(without)

    def test_a_missing_logo_never_blocks_sealing(self, sample_pdf, settings):
        """A brand file that is not there is not a reason to fail a seal."""
        settings.cover_logo = "/no/such/logo.png"
        sealed, info = seal_bytes(sample_pdf, settings)
        assert info["cover_page"] is True
        assert verify_bytes(sealed, settings)["verdict"] == "PASS"

    def test_a_broken_logo_file_never_blocks_sealing(self, sample_pdf, settings, tmp_path):
        broken = tmp_path / "CommLocker_logo_transparent.png"
        broken.write_bytes(b"this is not an image")
        settings.cover_logo = str(broken)
        sealed, _ = seal_bytes(sample_pdf, settings)
        assert verify_bytes(sealed, settings)["verdict"] == "PASS"

    def test_the_configured_path_wins(self, png_logo):
        from verifier.coverpage import find_cover_logo

        assert find_cover_logo(png_logo) == png_logo

    def test_a_configured_path_that_does_not_exist_resolves_to_nothing(self):
        from verifier.coverpage import find_cover_logo

        assert find_cover_logo("/no/such/file.png") is None
