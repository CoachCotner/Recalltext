#!/usr/bin/env python3
"""
The CommChecker demo: seal a record, verify it, tamper with one message,
verify again and watch the tool name the exact record that moved.

    python demo.py

Everything happens in memory except the three PDFs it writes so you can open
them yourself.
"""
import os

from verifier import (
    load_settings,
    quiet_library_logs,
    seal_bytes,
    verify_bytes,
)
from verifier.certs import ensure_demo_cert
from verifier.sample import make_sample_pdf

BAR = "=" * 72
GLYPH = {True: "[ok]", False: "[X ]", None: "[? ]"}


def show(report: dict) -> None:
    print(f"\n  VERDICT: {report.get('headline', report['verdict'])}  -  "
          f"{report['message']}")
    for check in report["checks"]:
        print(f"    {GLYPH[check['ok']]} {check['check']}: {check['detail']}")


def run() -> None:
    quiet_library_logs()
    settings = load_settings()

    print(BAR)
    print("  COMMCHECKER  -  Computer #2")
    print(BAR)

    ensure_demo_cert(settings)
    print(f"\nSigning mode: {settings.mode}")
    print(f"Timestamp authority: {settings.tsa_url or 'disabled'}")

    # ---------------------------------------------------------------
    print("\nStep 1 - The phone (Computer #1) exports and seals the record.")
    original = make_sample_pdf()
    sealed, info = seal_bytes(
        original, settings, source={"case_ref": "412 Maple Street"}
    )
    with open("sample.pdf", "wb") as f:
        f.write(original)
    with open("sealed.pdf", "wb") as f:
        f.write(sealed)
    print(f"  -> sealed.pdf written")
    print(f"     {info['records_sealed']} records fingerprinted into the manifest")
    print(f"     timestamp: {info['timestamp_note']}")

    # ---------------------------------------------------------------
    print("\nStep 2 - CommChecker verifies the untouched record.")
    show(verify_bytes(sealed, settings, "sealed.pdf"))

    # ---------------------------------------------------------------
    print("\nStep 3 - Someone edits the PDF to move a meeting from 2 to 5.")
    tampered = sealed.replace(b"tomorrow at 2.", b"tomorrow at 5.")
    if tampered == sealed:
        print("  (the sample text changed - skipping the tamper step)")
        return
    with open("tampered.pdf", "wb") as f:
        f.write(tampered)
    print("  -> tampered.pdf written (one line of text changed)")

    # ---------------------------------------------------------------
    print("\nStep 4 - CommChecker verifies the edited record.")
    report = verify_bytes(tampered, settings, "tampered.pdf")
    show(report)

    changed = report["records"].get("changed") or []
    if changed:
        print("\n  WHICH RECORD CHANGED:")
        for item in changed:
            print(f"    Record {item['id']}, page {item['page']}")
            print(f"    sent {item['sent_utc']} | {item['direction']} | {item['party']}")
            print(f"    {item['what_happened']}")
            print(f"      when sealed : {item['sealed_text']}")
            print(f"      in this file: {item['current_text']}")

    # ---------------------------------------------------------------
    print("\nStep 5 - Someone opens the sealed PDF and saves it again.")
    print("         Nothing is edited - the file is just rewritten.")
    resaved = _resave(sealed)
    with open("resaved.pdf", "wb") as f:
        f.write(resaved)
    print("  -> resaved.pdf written")

    print("\nStep 6 - CommChecker verifies the re-saved copy.")
    resaved_report = verify_bytes(resaved, settings, "resaved.pdf")
    show(resaved_report)
    print(
        "\n  Note the difference: this one is not an accusation. The content "
        "still\n  matches every sealed fingerprint, so it asks for the "
        "original file\n  rather than raising an alarm."
    )

    print("\n" + BAR)
    print("  The seal proves something changed.")
    print("  The manifest proves exactly what - and what did NOT.")
    print(BAR)
    print(f"\n  Files written in {os.getcwd()}:")
    print("    sample.pdf    the export before sealing")
    print("    sealed.pdf    the sealed record        -> PASS")
    print("    resaved.pdf   opened and saved again   -> RE-FILE (routine)")
    print("    tampered.pdf  the doctored record      -> FAIL (escalate)")
    print()
    print("  To try these in the web interface:")
    print("    uvicorn web.app:app --reload")
    print("    then open http://127.0.0.1:8000 and drag each file in.")
    print()


def _resave(pdf_bytes: bytes) -> bytes:
    """
    Re-save a PDF the way a viewer application does.

    Rewrites the file structure while leaving every word intact. This is the
    single most common reason a genuine record fails its check.
    """
    import io

    import pikepdf

    with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
        out = io.BytesIO()
        pdf.save(out)
    return out.getvalue()


if __name__ == "__main__":
    run()
