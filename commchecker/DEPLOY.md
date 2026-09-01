# Deploying CommChecker

The web service is a single, stateless application. It has no database, writes
nothing to disk, and keeps an uploaded document in memory only for the length of
one request. That makes it about as easy to host as software gets — and it means
you can scale it by simply running more copies.

Read [CONFIGURATION.md](CONFIGURATION.md) first for what the settings mean. This
document covers where to put it.

---

## Before you go live — the checklist

1. `COMMCHECKER_MODE=production`
2. Your real `.p12` certificate installed, and its password set
3. `COMMCHECKER_TRUST_SYSTEM_ROOTS=1`
4. A timestamp authority configured (the default is fine)
5. Served over **HTTPS** — your host almost certainly does this for you
6. Visit `/healthz`; it must return `{"status": "ok"}`
7. Visit `/config`; confirm it says `production`
8. Upload a known-good sealed PDF and confirm **PASS**, then a tampered one and
   confirm **FAIL**

Step 8 is the one people skip. Do not skip it.

---

## Option A — Docker (works anywhere)

```bash
docker build -t commchecker .

docker run -p 8000:8000 \
  -e COMMCHECKER_MODE=production \
  -e COMMCHECKER_P12_PATH=/secrets/signing.p12 \
  -e COMMCHECKER_P12_PASSWORD="..." \
  -e COMMCHECKER_TRUST_SYSTEM_ROOTS=1 \
  -v /path/to/your/cert.p12:/secrets/signing.p12:ro \
  commchecker
```

The `-v ... :ro` mounts your certificate into the container **read-only** at run
time. This is the right way to do it: the certificate is never copied into the
image, so the image itself holds no key material and is safe to store in a
registry.

The image runs as an unprivileged user and includes a health check.

---

## Option B — Render, Railway, Fly.io and similar

These hosts build from your Git repository and handle HTTPS for you.

1. Point the host at this repository, with `commchecker/` as the root directory.
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn web.app:app --host 0.0.0.0 --port $PORT`
   (the included `Procfile` already says this)
4. Add the environment variables from the checklist above.
5. Because these hosts have **no permanent disk**, supply the certificate as
   base64 text rather than a file:
   ```bash
   base64 -w0 commlocker-signing.p12
   ```
   Paste the result into `COMMCHECKER_P12_BASE64`.
6. Set the health check path to `/healthz`.

---

## Option C — Your own server

```bash
git clone <this repo> && cd commchecker
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

uvicorn web.app:app --host 127.0.0.1 --port 8000 --workers 4
```

Put Nginx or Caddy in front of it to terminate HTTPS, and run it under systemd
so it restarts on reboot. Bind uvicorn to `127.0.0.1`, not `0.0.0.0`, so only
the reverse proxy can reach it directly.

A minimal systemd unit:

```ini
[Unit]
Description=CommChecker
After=network.target

[Service]
User=commchecker
WorkingDirectory=/opt/commchecker
EnvironmentFile=/etc/commchecker/env
ExecStart=/opt/commchecker/venv/bin/uvicorn web.app:app \
  --host 127.0.0.1 --port 8000 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
```

Put the settings in `/etc/commchecker/env`, one `NAME=value` per line, and
restrict it: `chmod 600`, owned by root. It holds the certificate password.

---

## Scaling

Requests are independent and nothing is shared between them, so run as many
copies as you like behind any load balancer. Sizing notes:

- Verification is CPU work, not I/O. Roughly one worker per CPU core.
- Peak memory per request is a few times the size of the uploaded PDF.
  `COMMCHECKER_MAX_UPLOAD_MB` (default 25) is what bounds it — the service stops
  reading an oversized upload rather than buffering it and rejecting it later.

---

## What the service exposes

| Path | Purpose |
|---|---|
| `/` | The verification page |
| `/verify` | `POST` a PDF, get a JSON report |
| `/healthz` | Liveness plus configuration status — use this for health checks |
| `/config` | The running configuration, secrets redacted |

`/healthz` returns HTTP **503** when the configuration is broken, so a
misconfigured deployment fails your health check immediately rather than
failing silently on every upload.

`/config` is deliberately public and deliberately redacted: it is how you
confirm a live deployment is really in production mode. If you would rather not
expose it, block the path at your reverse proxy.

---

## Security notes

- **The certificate is the crown jewels.** Anyone holding the `.p12` and its
  password can produce seals indistinguishable from yours. Mount it read-only,
  restrict who can read it, and rotate it if you suspect exposure.
- `.gitignore` blocks `*.p12`, `*.pfx`, `*.pem`, `*.key` and `.env`. Do not
  override this.
- The service sets a strict Content-Security-Policy, `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff` and `Cache-Control: no-store` on every
  response.
- There are no accounts and no authentication. Anyone who can reach the page can
  check a document. That is usually what you want for a public verifier — put it
  behind your reverse proxy's access control if it is not.
- Uploaded documents are never written to disk and never logged. This is
  enforced by tests in `tests/test_web.py::TestNothingIsStored`.

---

## Upgrading a live deployment

Deploy the new version alongside the old one, check `/healthz` and `/config` on
the new instance, verify a known-good sealed PDF against it, then switch traffic
over. Sealed documents are not affected by upgrades — a seal is verified with
the certificate and timestamp it was made with, not with today's settings.
