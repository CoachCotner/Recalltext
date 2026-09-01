#!/usr/bin/env python3
"""
CommChecker command line.

  python cli.py init                    Create the demo signing certificate
  python cli.py config                  Show the current configuration
  python cli.py sample out.pdf          Build a sample export to play with
  python cli.py seal in.pdf out.pdf     Apply the seal (+ trusted timestamp)
  python cli.py verify file.pdf         Check a file  ->  PASS / FAIL
  python cli.py manifest file.pdf       Print the sealed per-record manifest
  python cli.py demo                    The whole story, start to finish

'verify' exits 0 on PASS and 1 on FAIL, so it can be used in a script.
"""
import json
import sys

from verifier import (
    ConfigError,
    SealError,
    load_settings,
    make_demo_cert,
    quiet_library_logs,
    read_manifest,
    seal,
    verify,
)
from verifier.certs import ensure_demo_cert

GLYPH = {True: "[ok]", False: "[X ]", None: "[? ]"}


def _print_report(report: dict) -> None:
    """Human-readable output. Use --json for the machine-readable version."""
    verdict = report["verdict"]
    print()
    print(f"  VERDICT: {verdict}  -  {report['message']}")
    print()
    for check in report["checks"]:
        print(f"    {GLYPH[check['ok']]} {check['check']}")
        print(f"         {check['detail']}")

    records = report.get("records") or {}
    findings = (
        (records.get("changed") or [])
        + (records.get("missing") or [])
        + (records.get("added") or [])
    )
    if findings:
        print()
        print("  WHAT CHANGED:")
        for item in findings:
            page = f", page {item['page']}" if item.get("page") else ""
            print(f"    Record {item['id']}{page}")
            meta = " | ".join(
                str(item[k]) for k in ("sent_utc", "direction", "party") if item.get(k)
            )
            if meta:
                print(f"      {meta}")
            print(f"      {item['what_happened']}")
            if item.get("sealed_text"):
                print(f"      when sealed : {item['sealed_text']}")
            if item.get("current_text"):
                print(f"      in this file: {item['current_text']}")

    timestamp = report.get("timestamp") or {}
    if timestamp.get("present"):
        trust = "trusted" if timestamp.get("trusted") else "authority not verified"
        print()
        print(f"  Trusted timestamp: {timestamp.get('time_utc')} ({trust})")

    for warning in report.get("warnings", []):
        print(f"\n  ! {warning}")

    print()
    print(f"  file SHA-256: {report['file_sha256']}")
    print()


def main() -> int:
    quiet_library_logs()

    argv = [a for a in sys.argv[1:] if a != "--json"]
    as_json = "--json" in sys.argv

    if not argv:
        print(__doc__)
        return 0

    command = argv[0]
    settings = load_settings()

    try:
        if command == "init":
            path = make_demo_cert(
                settings.demo_p12_path, settings.demo_p12_password
            )
            print(f"Created the DEMO signing certificate: {path}")
            print(
                "This is self-signed and for local testing only. See "
                "CONFIGURATION.md to switch to a real CA certificate."
            )
            return 0

        if command == "config":
            description = settings.describe()
            problems = settings.validate()
            if as_json:
                print(json.dumps({**description, "problems": problems}, indent=2))
                return 0 if not problems else 1
            print()
            for key, value in description.items():
                if key == "problems":
                    continue
                print(f"  {key.replace('_', ' '):<24} {value}")
            print()
            if problems:
                print("  PROBLEMS:")
                for problem in problems:
                    print(f"    - {problem}")
                print()
                return 1
            print("  Configuration looks usable.")
            print()
            return 0

        if command == "sample":
            from verifier.sample import make_sample_pdf

            out = argv[1] if len(argv) > 1 else "sample.pdf"
            with open(out, "wb") as f:
                f.write(make_sample_pdf())
            print(f"Wrote a sample export: {out}")
            return 0

        if command == "seal":
            if len(argv) < 3:
                print("Usage: python cli.py seal in.pdf out.pdf")
                return 2
            ensure_demo_cert(settings)
            info = seal(argv[1], argv[2], settings)
            if as_json:
                print(json.dumps(info, indent=2))
            else:
                print(f"Sealed -> {info['output']}")
                print(f"  records in manifest : {info['records_sealed']}")
                print(f"  sealed by           : {info['signer_subject']}")
                print(f"  timestamp           : {info['timestamp_note']}")
            return 0

        if command == "verify":
            if len(argv) < 2:
                print("Usage: python cli.py verify file.pdf")
                return 2
            ensure_demo_cert(settings)
            report = verify(argv[1], settings)
            if as_json:
                print(json.dumps(report, indent=2))
            else:
                _print_report(report)
            return 0 if report["verdict"] == "PASS" else 1

        if command == "manifest":
            if len(argv) < 2:
                print("Usage: python cli.py manifest file.pdf")
                return 2
            with open(argv[1], "rb") as f:
                manifest = read_manifest(f.read())
            if manifest is None:
                print("This file carries no CommLocker manifest.")
                return 1
            print(json.dumps(manifest, indent=2))
            return 0

        if command == "demo":
            import demo

            demo.run()
            return 0

    except (ConfigError, SealError) as e:
        print(f"\nERROR: {e}\n", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"\nERROR: file not found - {e.filename}\n", file=sys.stderr)
        return 2

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
