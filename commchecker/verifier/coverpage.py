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

# ---------------------------------------------------------------------------
# The approved design
#
# The layout was signed off as an HTML comp 1000px wide. Rather than reinvent
# the proportions, every measurement below is the design's own pixel value,
# scaled to the page by SCALE. That keeps this file readable against the comp:
# a 44px headline in the design is px(44) here.
#
# It is drawn with reportlab rather than rendered from the HTML on purpose.
# Sealing has to stay light enough to run wherever exports are produced, and
# shipping a headless browser into that path to draw one page is a bad trade.
# ---------------------------------------------------------------------------
def _rgb(hex_colour: str):
    hex_colour = hex_colour.lstrip("#")
    return tuple(int(hex_colour[i : i + 2], 16) / 255 for i in (0, 2, 4))


NAVY = _rgb("#071B42")
BURNT = _rgb("#C56230")
BURNT2 = _rgb("#E08A52")
BEIGE = _rgb("#F4F1EC")
INK = _rgb("#0E2038")
BODY = _rgb("#4A5876")
MUTED = _rgb("#8494AE")
LINE = _rgb("#E4DED3")
GREEN = _rgb("#1FA34B")
AMBER = _rgb("#D9932A")
RED = _rgb("#D8402F")
WHITE = (1, 1, 1)
PILL_BG = _rgb("#FBEEE3")
PILL_BORDER = _rgb("#E3C9B6")

PAGE_WIDTH, PAGE_HEIGHT = letter
DESIGN_WIDTH = 1000.0
SCALE = PAGE_WIDTH / DESIGN_WIDTH


def px(value: float) -> float:
    """A measurement from the design comp, in points."""
    return value * SCALE


PAD_X = px(54)


# ---------------------------------------------------------------------------
# Inter, the design's typeface
# ---------------------------------------------------------------------------
FONT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "brand", "fonts"
)
_INTER_WEIGHTS = {
    "Inter": "Inter-Regular.ttf",
    "Inter-SemiBold": "Inter-SemiBold.ttf",
    "Inter-Bold": "Inter-Bold.ttf",
    "Inter-ExtraBold": "Inter-ExtraBold.ttf",
    "Inter-Black": "Inter-Black.ttf",
}
# Used when the font files are absent, so a cover page still renders.
_FALLBACK = {
    "Inter": "Helvetica",
    "Inter-SemiBold": "Helvetica",
    "Inter-Bold": "Helvetica-Bold",
    "Inter-ExtraBold": "Helvetica-Bold",
    "Inter-Black": "Helvetica-Bold",
}
_fonts_ready = None


def _register_fonts() -> bool:
    """Register Inter once. Returns False if the files are not available."""
    global _fonts_ready
    if _fonts_ready is not None:
        return _fonts_ready

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    try:
        for name, filename in _INTER_WEIGHTS.items():
            path = os.path.join(FONT_DIR, filename)
            if not os.path.exists(path):
                _fonts_ready = False
                return False
            pdfmetrics.registerFont(TTFont(name, path))
        _fonts_ready = True
    except Exception:
        _fonts_ready = False
    return _fonts_ready


def font(name: str) -> str:
    """Resolve a design font name to whatever is actually available."""
    return name if _register_fonts() else _FALLBACK[name]

TIMESTAMP_FILENAME = "commlocker-timestamp.tsr"

# The cover page is the CommLocker product's page - CommLocker seals the
# record, CommChecker checks it - so it carries the CommLocker mark.
#
# Tried in order. The transparent PNG comes first: it is the one made to sit on
# a dark background, which is what the navy header band is, and at 1330px wide
# it has resolution to spare for a 250pt placement (~1040px at 300dpi).
#
# The 2000px PNG outranks the .svg deliberately. That SVG contains no vector
# paths - it is a base64 PNG wrapped in an <svg> element - so it offers no
# crispness advantage over a plain PNG while adding a rendering dependency. If
# a true vector file is supplied later, point COMMCHECKER_COVER_LOGO at it.
#
# Logos are placed exactly as supplied: never recoloured, traced or regenerated.
BRAND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "brand")
COVER_LOGO_CANDIDATES = (
    "CommLocker_logo_transparent.png",
    "CommLocker_logo_2000.png",
    "CommLocker_logo_POP.svg",
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
# ---------------------------------------------------------------------------
# Small drawing helpers, so the layout code below reads like the design
# ---------------------------------------------------------------------------
def _top(v: float) -> float:
    """Design y (measured down from the top edge) as a PDF coordinate."""
    return PAGE_HEIGHT - px(v)


def _width_of(text: str, font_name: str, size: float, tracking: float = 0) -> float:
    from reportlab.pdfbase import pdfmetrics

    width = pdfmetrics.stringWidth(text, font_name, size)
    if tracking and text:
        width += tracking * (len(text) - 1)
    return width


def _draw_text(c, x, y, text, font_name, size, colour, tracking=0, align="left"):
    """
    Draw a single line, optionally letter-spaced.

    Character spacing lives on the text object rather than the canvas in this
    reportlab, so tracked text goes through beginText.
    """
    width = _width_of(text, font_name, size, tracking)
    if align == "right":
        x -= width
    elif align == "center":
        x -= width / 2

    c.setFillColorRGB(*colour)
    if tracking:
        text_object = c.beginText(x, y)
        text_object.setFont(font_name, size)
        text_object.setCharSpace(tracking)
        text_object.textOut(text)
        c.drawText(text_object)
    else:
        c.setFont(font_name, size)
        c.drawString(x, y, text)


def _ch(font_name: str, size: float, count: float) -> float:
    """The design's `ch` unit: the advance width of "0"."""
    return _width_of("0", font_name, size) * count


def _wrap(text: str, font_name: str, size: float, width: float):
    return simpleSplit(text, font_name, size, width)


def _wrap_runs(runs, size: float, width: float):
    """
    Wrap a paragraph made of mixed weights.

    The chip copy leads with a bold clause and continues in regular, so words
    have to flow across the weight change rather than being laid out twice.
    """
    words = []
    for text, font_name in runs:
        for word in text.split():
            words.append((word, font_name))

    lines, current, current_width = [], [], 0.0
    for word, font_name in words:
        # The space before a word is drawn in that word's font, so it has to be
        # measured in that font too.
        extra = _width_of(word if not current else " " + word, font_name, size)
        if current and current_width + extra > width:
            lines.append(current)
            current, current_width = [(word, font_name)], _width_of(
                word, font_name, size
            )
        else:
            current.append((word, font_name))
            current_width += extra
    if current:
        lines.append(current)
    return lines


def _draw_runs(c, x, y, line, size, colours):
    """
    Draw one wrapped line of mixed-weight text.

    Uses a text object so reportlab advances the cursor itself. Doing that
    arithmetic by hand is what ran the words together.
    """
    text_object = c.beginText(x, y)
    current_font = None
    for index, (word, font_name) in enumerate(line):
        if font_name != current_font:
            text_object.setFont(font_name, size)
            text_object.setFillColorRGB(*colours[font_name])
            current_font = font_name
        text_object.textOut((" " if index else "") + word)
    c.drawText(text_object)


def _display_host(url: str) -> str:
    """commchecker.com - the address a person reads, not the full URL."""
    host = url.split("//")[-1].split("/")[0]
    return host[4:] if host.startswith("www.") else host


# ---------------------------------------------------------------------------
# The cover page
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
    """Render the one-page cover as PDF bytes, to the approved design."""
    _register_fonts()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter, pageCompression=0)
    c.setTitle("Sealed record - verification cover page")

    # Page ground
    c.setFillColorRGB(*BEIGE)
    c.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)

    _draw_header(c, demo_mode, logo_path)
    footer_top = _draw_footer(c, demo_mode)
    _draw_body(
        c,
        verify_url=verify_url,
        record_count=record_count,
        sealed_time=sealed_time,
        signer=signer,
        reference=reference,
        timestamp_authority=timestamp_authority,
        footer_top=footer_top,
    )

    c.save()
    return buffer.getvalue()


HEADER_HEIGHT = 144.0   # 34 padding + 76 logo + 34 padding
RULE_HEIGHT = 5.0


def _draw_header(c, demo_mode: bool, logo_path: Optional[str]) -> None:
    c.setFillColorRGB(*NAVY)
    c.rect(
        0,
        PAGE_HEIGHT - px(HEADER_HEIGHT),
        PAGE_WIDTH,
        px(HEADER_HEIGHT),
        stroke=0,
        fill=1,
    )

    # CommLocker's mark: CommLocker seals the record, so this is its page.
    drew_logo = False
    if logo_path:
        drew_logo = _draw_logo(
            c,
            logo_path,
            PAD_X,
            _top(34 + 76),          # 34px padding, 76px tall
            max_width=px(300),
            max_height=px(76),
        )
    if not drew_logo:
        _draw_text(
            c, PAD_X, _top(88), "COMMLOCKER", font("Inter-Black"), px(30), WHITE,
            tracking=px(1),
        )

    right = PAGE_WIDTH - PAD_X
    _draw_text(
        c, right, _top(62), "TAMPER-EVIDENT SEAL", font("Inter-ExtraBold"),
        px(13), BURNT2, tracking=px(3), align="right",
    )
    _draw_text(
        c, right, _top(104), "Sealed Record", font("Inter-Black"), px(38),
        WHITE, tracking=px(-0.5), align="right",
    )

    # The burnt divider, drawn as a burnt -> burnt2 gradient.
    slices = 160
    slice_width = PAGE_WIDTH / slices
    for i in range(slices):
        t = i / (slices - 1)
        colour = tuple(BURNT[j] + (BURNT2[j] - BURNT[j]) * t for j in range(3))
        c.setFillColorRGB(*colour)
        c.rect(
            i * slice_width,
            PAGE_HEIGHT - px(HEADER_HEIGHT + RULE_HEIGHT),
            slice_width + 0.6,
            px(RULE_HEIGHT),
            stroke=0,
            fill=1,
        )


def _draw_footer(c, demo_mode: bool) -> float:
    """Footer sits at the bottom of the page. Returns its top edge, in points."""
    disclaimer = (
        "The seal proves this file is unchanged since sealing \u2014 it does "
        "not vouch for what the records say."
    )
    size = px(13)
    body_font = font("Inter")
    lines = _wrap(disclaimer, body_font, size, _ch(body_font, size, 64))
    line_height = px(13 * 1.4)

    pill_height = px(11 * 1.2 + 12)
    content_height = max(len(lines) * line_height, pill_height)
    top = px(30) + content_height + px(20)

    c.setFillColorRGB(*LINE)
    c.rect(PAD_X, top, PAGE_WIDTH - 2 * PAD_X, 0.7, stroke=0, fill=1)

    y = top - px(20) - size
    for line in lines:
        _draw_text(c, PAD_X, y, line, body_font, size, MUTED)
        y -= line_height

    if demo_mode:
        label = "DEMO \u00b7 NOT A LIVE SEAL"
        pill_font = font("Inter-ExtraBold")
        pill_size = px(11)
        tracking = px(1)
        text_width = _width_of(label, pill_font, pill_size, tracking)
        pill_width = text_width + px(28)
        pill_x = PAGE_WIDTH - PAD_X - pill_width
        pill_y = top - px(20) - pill_height
        c.setFillColorRGB(*PILL_BG)
        c.setStrokeColorRGB(*PILL_BORDER)
        c.setLineWidth(0.7)
        c.roundRect(
            pill_x, pill_y, pill_width, pill_height, px(20), stroke=1, fill=1
        )
        _draw_text(
            c, pill_x + px(14), pill_y + px(7), label, pill_font, pill_size,
            BURNT, tracking=tracking,
        )

    return top


def _draw_body(
    c, verify_url, record_count, sealed_time, signer, reference,
    timestamp_authority, footer_top,
) -> None:
    content_width = PAGE_WIDTH - 2 * PAD_X
    y = _top(HEADER_HEIGHT + RULE_HEIGHT + 44)

    # -- eyebrow ----------------------------------------------------------
    eyebrow_font = font("Inter-ExtraBold")
    _draw_text(
        c, PAD_X, y - px(13), "COMMLOCKER \u00b7 SEALED & VERIFIABLE", eyebrow_font,
        px(13), BURNT, tracking=px(2.5),
    )
    y -= px(13 + 12)

    # -- headline ---------------------------------------------------------
    h1_font = font("Inter-Black")
    h1_size = px(44)
    h1_lines = _wrap(
        "This record can't be changed without showing it.",
        h1_font, h1_size, _ch(h1_font, h1_size, 15),
    )
    for line in h1_lines:
        y -= h1_size
        _draw_text(c, PAD_X, y, line, h1_font, h1_size, INK, tracking=px(-1))
        y -= px(44 * 1.05) - h1_size
    y -= px(14)

    # -- lead -------------------------------------------------------------
    lead_font = font("Inter")
    lead_size = px(18)
    lead_lines = _wrap(
        "Anyone can check it in seconds. If a single character changed since "
        "it was sealed, the check says so \u2014 and names the record that "
        "changed.",
        lead_font, lead_size, _ch(lead_font, lead_size, 46),
    )
    for line in lead_lines:
        y -= lead_size
        _draw_text(c, PAD_X, y, line, lead_font, lead_size, BODY)
        y -= px(18 * 1.5) - lead_size

    # -- facts + QR card --------------------------------------------------
    y -= px(34)
    card_width = px(262)
    card_x = PAGE_WIDTH - PAD_X - card_width
    facts_width = content_width - px(40) - card_width

    card_height = _draw_qr_card(c, verify_url, card_x, y, card_width)
    facts_height = _draw_facts(
        c, PAD_X, y, facts_width,
        _fact_rows(record_count, sealed_time, signer, reference, timestamp_authority),
    )
    y -= max(card_height, facts_height)

    # -- how to read a check ----------------------------------------------
    # The comp is a web page; a Letter sheet is proportionally taller. Rather
    # than leave a void at the bottom, this block is anchored above the footer
    # and the slack falls between the facts and the chips as white space.
    layout = _chip_layout(content_width)
    label_block = px(13 + 14)
    natural_top = y - px(38)
    lowest_top = footer_top + px(40) + layout["height"] + label_block
    # Slack is shared between the space above the chips and the space below,
    # so neither reads as a gap somebody forgot to fill.
    slack = max(natural_top - lowest_top, 0)
    chips_top = natural_top - slack / 2

    _draw_text(
        c, PAD_X, chips_top - px(13), "HOW TO READ A CHECK", eyebrow_font,
        px(13), BURNT, tracking=px(2.5),
    )
    _draw_chips(c, PAD_X, chips_top - label_block, content_width, layout)


def _fact_rows(record_count, sealed_time, signer, reference, timestamp_authority):
    rows = []
    if reference:
        rows.append(("Reference", reference))
    rows.append(("Records sealed", str(record_count)))
    if sealed_time:
        rows.append(("Sealed", sealed_time.strftime("%d %b %Y \u00b7 %H:%M UTC")))
        rows.append(
            ("Time certified by", timestamp_authority or "RFC-3161 authority")
        )
    else:
        rows.append(("Sealed", "no trusted timestamp on this seal"))
    if signer:
        rows.append(("Sealed by", signer))
    return rows


def _draw_facts(c, x, top, width, rows) -> float:
    key_font = font("Inter-SemiBold")
    value_font = font("Inter-Bold")
    size = px(16)
    pad = px(14)
    row_height = pad + size + pad

    # top border on the first row
    c.setFillColorRGB(*LINE)
    c.rect(x, top, width, 0.7, stroke=0, fill=1)

    y = top
    for key, value in rows:
        baseline = y - pad - size * 0.82
        _draw_text(c, x, baseline, key, key_font, size, MUTED, tracking=px(0.3))

        # Long values are trimmed rather than allowed to collide with the key.
        available = width - _width_of(key, key_font, size, px(0.3)) - px(20)
        shown = value
        while shown and _width_of(shown, value_font, size) > available:
            shown = shown[:-2]
            if len(shown) < 4:
                break
        if shown != value:
            shown = shown.rstrip() + "..."
        _draw_text(c, x + width, baseline, shown, value_font, size, INK, align="right")

        y -= row_height
        c.setFillColorRGB(*LINE)
        c.rect(x, y, width, 0.7, stroke=0, fill=1)

    return top - y


def _draw_qr_card(c, verify_url, x, top, width) -> float:
    pad = px(22)
    qr_size = px(170)
    cap_size = px(11)
    url_size = px(18)
    height = pad + qr_size + px(14) + cap_size + px(3) + url_size + pad

    c.setFillColorRGB(*WHITE)
    c.setStrokeColorRGB(*LINE)
    c.setLineWidth(0.7)
    c.roundRect(x, top - height, width, height, px(18), stroke=1, fill=1)

    _qr_block(c, verify_url, x + (width - qr_size) / 2, top - pad - qr_size, qr_size)

    centre = x + width / 2
    cap_y = top - pad - qr_size - px(14) - cap_size
    _draw_text(
        c, centre, cap_y, "SCAN TO VERIFY", font("Inter-ExtraBold"), cap_size,
        MUTED, tracking=px(2), align="center",
    )
    _draw_text(
        c, centre, cap_y - px(3) - url_size, _display_host(verify_url),
        font("Inter-ExtraBold"), url_size, NAVY, align="center",
    )
    return height


def _qr_block(c, verify_url: str, x: float, y: float, size: float) -> None:
    """Draw the QR code at an exact size, squared to the design's box."""
    widget = qr.QrCodeWidget(verify_url, barLevel="M")
    bounds = widget.getBounds()
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]

    drawing = Drawing(
        size, size, transform=[size / width, 0, 0, size / height, 0, 0]
    )
    drawing.add(widget)
    renderPDF.draw(drawing, c, x, y)


CHIPS = (
    ("PASS", GREEN, "Unchanged since sealing.", "File it."),
    (
        "RE-FILE",
        AMBER,
        "A re-saved copy.",
        "Content matches \u2014 ask for the original sealed export.",
    ),
    (
        "FAIL",
        RED,
        "Changed after sealing.",
        "The check names the record. Escalate.",
    ),
)


def _chip_layout(content_width):
    """Measure the chip row before drawing it, so it can be positioned first."""
    gap = px(16)
    chip_width = (content_width - 2 * gap) / 3
    pad = px(18)
    # A couple of points of slack: measured width and drawn width differ very
    # slightly, and without it a full line sits tight against the card edge.
    inner = chip_width - 2 * pad - px(6)

    body_font = font("Inter")
    bold_font = font("Inter-Bold")
    body_size = px(15)
    line_height = px(15 * 1.45)

    # One height for all three, so the row lines up like the grid it is.
    wrapped = [
        _wrap_runs([(lead, bold_font), (rest, body_font)], body_size, inner)
        for _, _, lead, rest in CHIPS
    ]
    text_lines = max(len(w) for w in wrapped)
    tag_height = px(5 + 15 * 1.2 + 5)
    height = pad + tag_height + px(12) + text_lines * line_height + px(20)
    return {
        "gap": gap, "chip_width": chip_width, "pad": pad, "wrapped": wrapped,
        "height": height, "line_height": line_height, "body_size": body_size,
        "tag_height": tag_height, "body_font": body_font, "bold_font": bold_font,
    }


def _draw_chips(c, x, top, content_width, layout=None) -> float:
    layout = layout or _chip_layout(content_width)
    gap = layout["gap"]
    chip_width = layout["chip_width"]
    pad = layout["pad"]
    wrapped = layout["wrapped"]
    height = layout["height"]
    line_height = layout["line_height"]
    body_size = layout["body_size"]
    tag_height = layout["tag_height"]
    body_font = layout["body_font"]
    bold_font = layout["bold_font"]

    tag_font = font("Inter-Black")
    tag_size = px(15)
    colours = {body_font: BODY, bold_font: INK}

    for index, ((label, colour, _, _), lines) in enumerate(zip(CHIPS, wrapped)):
        chip_x = x + index * (chip_width + gap)
        c.setFillColorRGB(*WHITE)
        c.setStrokeColorRGB(*LINE)
        c.setLineWidth(0.7)
        c.roundRect(chip_x, top - height, chip_width, height, px(16), stroke=1, fill=1)

        tag_width = _width_of(label, tag_font, tag_size, px(1)) + px(24)
        tag_y = top - pad - tag_height
        c.setFillColorRGB(*colour)
        c.roundRect(chip_x + pad, tag_y, tag_width, tag_height, px(8), stroke=0, fill=1)
        _draw_text(
            c, chip_x + pad + px(12), tag_y + px(7), label, tag_font, tag_size,
            WHITE, tracking=px(1),
        )

        y = tag_y - px(12) - body_size
        for line in lines:
            _draw_runs(c, chip_x + pad, y, line, body_size, colours)
            y -= line_height

    return height


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
