"""
The self-verifying cover page.

A sealed export gets a front page that a person can read and act on without
knowing anything about cryptography: what this document is, how many records it
holds, when it was sealed, and a QR code that takes them to CommChecker to
check it for themselves.

Why this instead of integrating with a transaction platform: the cover page
travels with the file. It works in Paperless Pipeline, Dotloop, SkySlope, an
email attachment or a printout, and it keeps working when a vendor changes
their API. One piece of work instead of one per platform.

About the timestamp
-------------------
A document cannot contain a timestamp that covers itself - the timestamp would
change the document, which would change what the timestamp is over. So the time
printed here is a *content timestamp*: an RFC-3161 authority's signed statement
that these exact records existed at that moment, obtained before the seal is
applied. It is a real, independently checkable attestation, and it is about the
records, which is the part that matters. The seal then carries its own
timestamp a moment later, which is what CommChecker reports on verification.
"""
import hashlib
import io
import os
from datetime import datetime, timezone
from typing import Optional, Tuple

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

NAVY = (7 / 255, 27 / 255, 66 / 255)
BURNT = (197 / 255, 98 / 255, 48 / 255)
INK = (0.06, 0.09, 0.13)
MUTED = (0.35, 0.39, 0.47)
RULE = (0.85, 0.87, 0.91)

PAGE_WIDTH, PAGE_HEIGHT = letter
MARGIN = 62

TIMESTAMP_FILENAME = "commlocker-timestamp.tsr"

# The cover page is the CommLocker product's page - CommLocker seals the
# record, CommChecker checks it - so it carries the CommLocker mark.
#
# Tried in order. The transparent PNG comes first because it is the one made
# to sit on a dark background, which is what the navy header band is. Logos are
# placed exactly as supplied: never recoloured, traced or regenerated.
BRAND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "brand")
COVER_LOGO_CANDIDATES = (
    "CommLocker_logo_transparent.png",
    "CommLocker_logo_POP.svg",
    "CommLocker_logo_2000.png",
)


def find_cover_logo(configured: Optional[str] = None) -> Optional[str]:
    """
    Locate the CommLocker logo for the cover page header.

    Returns None when no logo file is present, in which case the cover page
    sets the wordmark in type instead - a missing brand file must never stop a
    document being sealed.
    """
    if configured:
        return configured if os.path.exists(configured) else None
    for name in COVER_LOGO_CANDIDATES:
        candidate = os.path.join(BRAND_DIR, name)
        if os.path.exists(candidate):
            return candidate
    return None


def _draw_logo(c, path: str, x: float, y: float, max_width: float, max_height: float) -> bool:
    """
    Place the logo file as-is. Returns False if it could not be drawn.

    Aspect ratio is preserved and the artwork is never altered - no recolouring,
    no tracing, no regeneration. An SVG is placed as vector so it stays crisp at
    any zoom or print size.
    """
    try:
        if path.lower().endswith(".svg"):
            from svglib.svglib import svg2rlg

            drawing = svg2rlg(path)
            if drawing is None:
                return False
            scale = min(max_width / drawing.width, max_height / drawing.height)
            drawing.scale(scale, scale)
            drawing.width *= scale
            drawing.height *= scale
            renderPDF.draw(drawing, c, x, y)
            return True

        from reportlab.lib.utils import ImageReader

        image = ImageReader(path)
        width, height = image.getSize()
        scale = min(max_width / width, max_height / height)
        c.drawImage(
            image,
            x,
            y,
            width=width * scale,
            height=height * scale,
            mask="auto",           # honour the file's own transparency
            preserveAspectRatio=True,
        )
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# The content timestamp
# ---------------------------------------------------------------------------
def content_timestamp(payload: bytes, timestamper) -> Tuple[Optional[datetime], Optional[bytes]]:
    """
    Ask the timestamp authority to certify that ``payload`` existed now.

    Returns (time, token_bytes), or (None, None) when timestamping is switched
    off or the authority cannot be reached. Sealing is never blocked by this -
    the caller decides how strict to be.
    """
    if timestamper is None:
        return None, None

    import asyncio

    digest = hashlib.sha256(payload).digest()
    try:
        token = asyncio.run(timestamper.async_timestamp(digest, "sha256"))
    except Exception:
        return None, None

    try:
        return _token_time(token), token.dump()
    except Exception:
        return None, None


def _token_time(token) -> Optional[datetime]:
    """Pull the authority's certified time out of an RFC-3161 token."""
    from asn1crypto import tsp

    try:
        encap = token["content"]["encap_content_info"]["content"]
        tst_info = tsp.TSTInfo.load(encap.parsed.dump())
        return tst_info["gen_time"].native
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render_cover_page(
    verify_url: str,
    record_count: int,
    sealed_time: Optional[datetime] = None,
    signer: str = "",
    reference: str = "",
    demo_mode: bool = False,
    timestamp_authority: str = "",
    logo_path: Optional[str] = None,
) -> bytes:
    """Render the one-page cover as PDF bytes."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter, pageCompression=0)
    c.setTitle("Sealed record - verification cover page")

    _header(c, demo_mode, logo_path)

    y = PAGE_HEIGHT - 178

    c.setFillColorRGB(*INK)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(MARGIN, y, "This document carries a tamper-evident seal.")
    y -= 24

    # The QR sits to the right; keep the text column clear of it.
    qr_size = 112
    qr_x = PAGE_WIDTH - MARGIN - qr_size
    qr_top = y + 6
    text_width = qr_x - MARGIN - 26

    c.setFillColorRGB(*MUTED)
    c.setFont("Helvetica", 11)
    for line in simpleSplit(
        "Anyone can check it independently. If a single character has changed "
        "since it was sealed, the check will say so and name the record that "
        "changed.",
        "Helvetica",
        11,
        text_width,
    ):
        c.drawString(MARGIN, y, line)
        y -= 15

    _qr_block(c, verify_url, qr_x, qr_top - qr_size, qr_size)

    # --- the link, spelled out for anyone who will not scan a code --------
    y = min(y - 16, qr_top - qr_size - 34)
    c.setFillColorRGB(*BURNT)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(MARGIN, y, "VERIFY THIS DOCUMENT AT")
    y -= 17
    c.setFillColorRGB(*NAVY)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(MARGIN, y, verify_url)
    y -= 26

    # --- the facts --------------------------------------------------------
    rows = [("Records sealed", f"{record_count}")]
    if reference:
        rows.insert(0, ("Reference", reference))
    if sealed_time:
        rows.append(("Sealed", sealed_time.strftime("%d %B %Y at %H:%M:%S UTC")))
        rows.append(
            (
                "Time certified by",
                timestamp_authority or "an RFC-3161 timestamp authority",
            )
        )
    else:
        rows.append(("Sealed", "no trusted timestamp on this seal"))
    if signer:
        rows.append(("Sealed by", signer))

    label_width = 150
    value_width = PAGE_WIDTH - 2 * MARGIN - label_width
    for label, value in rows:
        c.setFillColorRGB(*RULE)
        c.rect(MARGIN, y + 15, PAGE_WIDTH - 2 * MARGIN, 0.6, stroke=0, fill=1)
        c.setFillColorRGB(*MUTED)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(MARGIN, y, label.upper())
        c.setFillColorRGB(*INK)
        c.setFont("Helvetica", 11)
        lines = simpleSplit(value, "Helvetica", 11, value_width)[:2]
        for line in lines:
            c.drawString(MARGIN + label_width, y, line)
            y -= 14
        y -= 10

    # --- what to do with the answer ---------------------------------------
    y -= 14
    c.setFillColorRGB(*BURNT)
    c.rect(MARGIN, y + 20, 46, 2.5, stroke=0, fill=1)
    c.setFillColorRGB(*INK)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(MARGIN, y, "How to read the result")
    y -= 22

    guidance = [
        ("PASS", "Nothing has changed since this record was sealed. File it."),
        (
            "RE-FILE",
            "The content still matches, but this is not the original file - it "
            "was re-saved somewhere along the way. Ask for the original sealed "
            "export. This is routine, not a red flag.",
        ),
        (
            "FAIL",
            "The content changed after sealing. The result names which record "
            "changed and what it said before. Escalate this one.",
        ),
    ]
    for label, text in guidance:
        c.setFillColorRGB(*BURNT)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MARGIN, y, label)
        c.setFillColorRGB(*MUTED)
        c.setFont("Helvetica", 10)
        for line in simpleSplit(
            text, "Helvetica", 10, PAGE_WIDTH - 2 * MARGIN - 76
        ):
            c.drawString(MARGIN + 76, y, line)
            y -= 13.5
        y -= 9

    _footer(c, demo_mode)
    c.save()
    return buffer.getvalue()


def _header(c, demo_mode: bool, logo_path: Optional[str] = None) -> None:
    c.setFillColorRGB(*NAVY)
    c.rect(0, PAGE_HEIGHT - 130, PAGE_WIDTH, 130, stroke=0, fill=1)
    c.setFillColorRGB(*BURNT)
    c.rect(0, PAGE_HEIGHT - 135, PAGE_WIDTH, 5, stroke=0, fill=1)

    drew_logo = False
    if logo_path:
        drew_logo = _draw_logo(
            c, logo_path, MARGIN, PAGE_HEIGHT - 104, max_width=250, max_height=62
        )

    if drew_logo:
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 19)
        c.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 62, "SEALED RECORD")
        c.setFillColorRGB(0.78, 0.82, 0.89)
        c.setFont("Helvetica", 10.5)
        c.drawRightString(
            PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 80, "verify at CommChecker"
        )
    else:
        # No brand file present - set it in type rather than inventing artwork.
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 27)
        c.drawString(MARGIN, PAGE_HEIGHT - 68, "SEALED RECORD")
        c.setFillColorRGB(0.78, 0.82, 0.89)
        c.setFont("Helvetica", 12)
        c.drawString(
            MARGIN,
            PAGE_HEIGHT - 90,
            "CommLocker communication export - verify at CommChecker",
        )

    if demo_mode:
        c.setFillColorRGB(*BURNT)
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(
            PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 68, "DEMO - NOT A LIVE SEAL"
        )


def _qr_block(c, verify_url: str, x: float, y: float, size: float) -> None:
    widget = qr.QrCodeWidget(verify_url, barLevel="M")
    bounds = widget.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]

    drawing = Drawing(size, size, transform=[size / width, 0, 0, size / height, 0, 0])
    drawing.add(widget)
    renderPDF.draw(drawing, c, x, y)

    c.setFillColorRGB(*MUTED)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(x + size / 2, y - 13, "SCAN TO VERIFY")


def _footer(c, demo_mode: bool) -> None:
    c.setFillColorRGB(*RULE)
    c.rect(MARGIN, 74, PAGE_WIDTH - 2 * MARGIN, 0.6, stroke=0, fill=1)
    c.setFillColorRGB(*MUTED)
    c.setFont("Helvetica", 8.5)
    c.drawString(
        MARGIN,
        58,
        "The seal proves this file is unchanged since sealing. It does not "
        "vouch for what the records say.",
    )
    if demo_mode:
        c.drawString(
            MARGIN,
            45,
            "DEMO MODE - sealed with a self-signed certificate, for testing only.",
        )


# ---------------------------------------------------------------------------
# Attaching the cover to the export
# ---------------------------------------------------------------------------
def prepend_cover(cover_pdf: bytes, document_pdf: bytes) -> bytes:
    """
    Put the cover page in front of the export.

    Done before sealing, so the seal covers the cover page too - the QR code
    and the record count cannot be swapped out without breaking the seal.
    """
    import pikepdf

    with pikepdf.open(io.BytesIO(cover_pdf)) as cover:
        with pikepdf.open(io.BytesIO(document_pdf)) as document:
            for page in document.pages:
                cover.pages.append(page)
            output = io.BytesIO()
            # Leave the text layer uncompressed, matching how the export was
            # generated. It keeps the tamper demo legible - you can see the
            # edit in a hex editor - and costs a few kilobytes.
            cover.save(output, compress_streams=False)
    return output.getvalue()
