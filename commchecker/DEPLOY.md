# Deploying CommChecker

The web service is a single, stateless application. It has no database, writes
nothing to disk, and keeps an uploaded document in memory only for the length of
one request. That makes it about as easy to host as software gets — and it means
you can scale it by simply running more copies.

Read [CONFIGURATION.md](CONFIGURATION.md) first for what the settings mean. This
document covers where to put it.

---

## Hosting a demo (no certificate yet)

This is the quickest path to a real URL you can show people, using the demo
certificate. About ten minutes, and nothing to pay on a free tier.

**The one thing that trips people up:** a deployed server creates its own demo
certificate, and its filesystem is wiped on every deploy. A PDF you sealed on
your laptop is signed by a key that server has never seen, so it gets rejected
as coming from an unknown signer — correct, but unhelpful. The fix is to give
both machines the same demo certificate.

**On your laptop**, create the certificate and your two demo files:

```bash
cd commchecker
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

python demo.py
```

That writes three files: `sealed.pdf` (the good copy), `tampered.pdf` (the
doctored one), and `demo.p12` (the signing certificate).

Now turn the certificate into text you can paste into a hosting dashboard:

```bash
base64 -w0 demo.p12
```

On a Mac, use `base64 -i demo.p12`. Copy the whole line — it is long.

**On Render:**

1. Sign in at [render.com](https://render.com) and choose **New → Web Service**.
2. Connect the `CoachCotner/Recalltext` repository and pick the branch
   `claude/commlocker-new-step-vxm0pg`.
3. Set **Root Directory** to `commchecker`.
4. Set **Build Command** to `pip install -r requirements.txt`.
5. Set **Start Command** to `uvicorn web.app:app --host 0.0.0.0 --port $PORT`.
6. Under **Environment**, add one variable:
   `COMMCHECKER_DEMO_P12_BASE64` = the long line you copied.
7. Set **Health Check Path** to `/healthz`.
8. Create the service and wait for the first deploy to finish.

Railway is the same idea: New Project → Deploy from GitHub, pick the branch,
set the root directory to `commchecker`, add the same environment variable.
Railway reads the `Procfile`, so it needs no start command.

**Then set the verify URL.** Once Render gives you a URL, add one more
environment variable — `COMMCHECKER_VERIFY_URL` — set to that URL, on whatever
machine does the sealing. It is what the QR code on every sealed document
points at, so set it before you seal anything you plan to send out.

**Check it worked.** Visit `/healthz` — it should say
`{"status": "ok", "mode": "demo"}`. Then open the main page and drop in
`sealed.pdf` (expect **PASS**) and `tampered.pdf` (expect **FAIL**, naming
record 0003).

Demo mode is honest about itself: every result carries a note that the
certificate is self-signed and proves nothing about real-world identity, and
the footer reads *"Demo mode · self-signed certificate, for testing only."*
That is the right thing to have on screen in front of investors — it shows you
know the difference. When your CA certificate arrives, follow the checklist
below and those notes go away.

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
