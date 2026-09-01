"""
Building an export PDF that CommChecker can read record-by-record.

This is the contract between the phone app (Computer #1) and the verifier
(Computer #2). Every record is printed with a machine-readable header line:

    RECORD 0004 | 2025-08-11T14:32:00Z | INBOUND | +15550142
    Confirmed for tomorrow at 2.

The header is visible on the page - a human reads it as a numbered, timestamped
entry, and the verifier reads it as structured data. Nothing is hidden.

The production CommLocker exporter must emit records in exactly this shape.
"""
import io
from typing import List, Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

from .manifest import Record

NAVY = (7 / 255, 27 / 255, 66 / 255)
BURNT = (197 / 255, 98 / 255, 48 / 255)
GREY = (0.42, 0.45, 0.5)

PAGE_WIDTH, PAGE_HEIGHT = letter
MARGIN = 60
BODY_WIDTH = PAGE_WIDTH - 2 * MARGIN - 14
BOTTOM = 70


def record_header_line(record: Record) -> str:
    """The one line that makes a record machine-readable."""
    return (
        f"RECORD {record.id} | {record.sent_utc} | "
        f"{record.direction.upper()} | {record.party}"
    )


def render_records_pdf(
    records: List[Record],
    title: str = "CommLocker Export",
    subtitle: Optional[str] = None,
) -> bytes:
    """Render records to a PDF in memory and return the bytes."""
    buffer = io.BytesIO()
    # pageCompression=0 keeps the text layer uncompressed, which makes the
    # tamper demo legible - you can see the edit in a hex editor.
    c = canvas.Canvas(buffer, pagesize=letter, pageCompression=0)
    c.setTitle(title)

    page_number = 1
    y = _draw_page_furniture(c, title, subtitle, page_number)

    for record in records:
        header = record_header_line(record)
        body_lines = simpleSplit(record.body, "Helvetica", 11, BODY_WIDTH)
        needed = 16 + len(body_lines) * 14 + 14

        if y - needed < BOTTOM:
            c.showPage()
            page_number += 1
            y = _draw_page_furniture(c, title, subtitle, page_number)

        record.page = page_number

        c.setFillColorRGB(*BURNT)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(MARGIN, y, header)
        y -= 16

        c.setFillColorRGB(0.07, 0.09, 0.13)
        c.setFont("Helvetica", 11)
        for line in body_lines:
            c.drawString(MARGIN + 14, y, line)
            y -= 14
        y -= 14

    c.save()
    return buffer.getvalue()


def _draw_page_furniture(c, title: str, subtitle: Optional[str], page_number: int) -> float:
    """Navy header band and footer. Returns the y position to start writing at."""
    c.setFillColorRGB(*NAVY)
    c.rect(0, PAGE_HEIGHT - 74, PAGE_WIDTH, 74, stroke=0, fill=1)
    c.setFillColorRGB(*BURNT)
    c.rect(0, PAGE_HEIGHT - 78, PAGE_WIDTH, 4, stroke=0, fill=1)

    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(MARGIN, PAGE_HEIGHT - 42, title)
    if subtitle:
        c.setFont("Helvetica", 10)
        c.setFillColorRGB(0.80, 0.84, 0.90)
        c.drawString(MARGIN, PAGE_HEIGHT - 60, subtitle)

    c.setFillColorRGB(*GREY)
    c.setFont("Helvetica", 8)
    c.drawString(
        MARGIN,
        40,
        "Sealed with a CommLocker integrity seal. Verify at CommChecker.",
    )
    c.drawRightString(PAGE_WIDTH - MARGIN, 40, f"Page {page_number}")

    return PAGE_HEIGHT - 110


def sample_records() -> List[Record]:
    """A small, realistic transaction thread for demos and tests."""
    raw = [
        ("2025-08-08T15:12:00Z", "INBOUND", "+15550142",
         "Hi - following up on 412 Maple Street. Are the sellers open to a "
         "15 day close?"),
        ("2025-08-08T15:31:00Z", "OUTBOUND", "+15550142",
         "They are. I'll send the addendum tonight."),
        ("2025-08-11T14:32:00Z", "INBOUND", "+15550142",
         "Confirmed for tomorrow at 2."),
        ("2025-08-12T09:05:00Z", "OUTBOUND", "+15550142",
         "Appraisal came in at value. No repair credits requested."),
        ("2025-08-12T09:40:00Z", "INBOUND", "+15550142",
         "Understood. We accept the terms as written and waive the "
         "inspection contingency."),
        ("2025-08-14T11:02:00Z", "OUTBOUND", "+15550142",
         "Wire instructions come from the title company only. I will never "
         "email you new wire details."),
    ]
    return [
        Record(
            id=f"{i:04d}",
            sent_utc=sent,
            direction=direction,
            party=party,
            body=body,
        )
        for i, (sent, direction, party, body) in enumerate(raw, start=1)
    ]


def make_sample_pdf() -> bytes:
    """The demo export, in memory."""
    return render_records_pdf(
        sample_records(),
        title="CommLocker Export - 412 Maple Street",
        subtitle="Transaction thread - 6 records - exported 2025-08-15",
    )
