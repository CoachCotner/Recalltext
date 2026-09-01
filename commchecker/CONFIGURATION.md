# Configuration — every setting, in plain English

You do not edit code to configure CommChecker. You set **environment
variables** — named values the program reads when it starts.

Three ways to set them, all equivalent:

1. **A `.env` file.** Copy `.env.example` to `.env` and edit it.
2. **Your hosting dashboard.** Render, Railway, Fly.io and friends all have an
   "Environment Variables" screen. Add them there.
3. **The command line**, for one-off testing:
   ```bash
   COMMCHECKER_MODE=production python cli.py verify record.pdf
   ```

**To check what the program actually thinks its settings are**, run
`python cli.py config` — or, on a running web service, visit `/config`.
Both print the live configuration with every secret redacted. Use this whenever
something is not behaving the way you expect.

---

## 0. Two machines, two different jobs

Before any setting makes sense, the most important distinction in the system:

| Job | What it needs | Where it runs |
|---|---|---|
| **Sealing** — applying the seal to an export | Your **private key** (the `.p12`) | Wherever exports are made. Never public. |
| **Verifying** — checking a sealed document | The **public certificate** of whoever sealed it | The CommChecker website. Internet-facing. |

**Your private key never goes on the web server.** The verifier does not need
it and cannot use it. It only needs to know which authorities to trust, which
is public information.

This is why `python cli.py config` asks for a signing certificate only when you
are actually going to seal something. A verify-only deployment configures
cleanly with no private key at all.

So when your certificate arrives and you ask "where do I put it?" — the answer
is: on the machine that seals, and nowhere else. If someone gets your `.p12`
and its password, they can produce seals indistinguishable from yours, which is
exactly why it does not belong on a public server.

---

## 1. The signing certificate

> This is requirement #1: keep the demo certificate for local testing, and drop
> in a real one for production.

### The one setting that governs everything

| Setting | Values | Default |
|---|---|---|
| `COMMCHECKER_MODE` | `demo` or `production` | `demo` |

**`demo`** uses a self-signed certificate the tool generates for itself. Good
for local testing and demos. It proves a file is unchanged, but it does not
prove *who* sealed it — nothing in the outside world has any reason to trust a
certificate you made yourself. Adobe Reader shows a yellow warning for it.

**`production`** uses the certificate you bought from a Certificate Authority.

**A deliberate safety rule:** in production mode, CommChecker will *never*
quietly fall back to the demo certificate. If the real one is missing or the
password is wrong, it stops and tells you. A seal that looks valid to this tool
but was signed with a self-signed demo key is worse than no seal at all — it
gives false confidence.

### Buying the real certificate

You need a **document signing certificate** (sometimes called a *document
signer* or *AATL certificate*). This is not the same as the SSL certificate for
a website.

- Vendors: DigiCert, GlobalSign, Sectigo, Entrust.
- Cost: roughly **$210–$510 per year**.
- Ask for one on the **Adobe Approved Trust List (AATL)** if you want Adobe
  Reader to show a green tick automatically. This matters for anything a
  counterparty or a court will open.
- Expect identity verification — they will confirm your business exists. Allow
  a few days.

What you receive is a file ending in **`.p12`** (or `.pfx`) plus a password.
That file contains your private key. Treat it like the key to the building:
never email it, never commit it to Git (`.gitignore` already blocks `*.p12`),
and keep a backup somewhere safe.

### Installing it

| Setting | What it is |
|---|---|
| `COMMCHECKER_P12_PATH` | Full path to your `.p12` file |
| `COMMCHECKER_P12_PASSWORD` | The password the CA gave you |
| `COMMCHECKER_P12_PASSWORD_FILE` | *Alternative:* a file containing the password |
| `COMMCHECKER_P12_BASE64` | *Alternative:* the certificate as base64 text |
| `COMMCHECKER_P12_CHAIN_PATH` | Intermediate certificates, if the CA sent them separately |

The straightforward setup:

```bash
COMMCHECKER_MODE=production
COMMCHECKER_P12_PATH=/etc/commchecker/commlocker-signing.p12
COMMCHECKER_P12_PASSWORD=the-password-the-CA-gave-you
```

**If your host has no permanent disk** (Render, Railway, Heroku and similar
rebuild the filesystem on every deploy), you cannot store a file there. Convert
the certificate to text instead:

```bash
base64 -w0 commlocker-signing.p12
```

Paste the (long) output into `COMMCHECKER_P12_BASE64` and leave
`COMMCHECKER_P12_PATH` unset. Set one or the other, never both.

**If your host has a secrets manager**, put the password in a mounted secret
file and point `COMMCHECKER_P12_PASSWORD_FILE` at it. A trailing newline is
ignored, because text editors add them by accident.

### Demo certificate settings

Only used when `COMMCHECKER_MODE=demo`.

| Setting | Default |
|---|---|
| `COMMCHECKER_DEMO_P12_PATH` | `demo.p12` |
| `COMMCHECKER_DEMO_P12_PASSWORD` | `demo` |
| `COMMCHECKER_DEMO_P12_BASE64` | *(unset)* - the demo certificate as text |

Create it with `python cli.py init`. The demo and the web service create it
automatically if it is missing.

**If you are hosting a demo, you need `COMMCHECKER_DEMO_P12_BASE64`.** A
deployed server creates its own demo certificate and loses it on every deploy,
so a PDF you sealed on your laptop is signed by a key the server has never
seen - and gets correctly rejected as coming from an unknown signer. Give both
machines the same certificate:

```bash
python cli.py init      # creates demo.p12 on your laptop
base64 -w0 demo.p12     # copy this into COMMCHECKER_DEMO_P12_BASE64 on the host
```

This does not weaken anything: a document sealed with any *other* key is still
rejected.

---

## 2. The trusted timestamp

> This is requirement #2.

**What it does.** At sealing time, CommChecker sends a timestamp authority a
hash of the signature — **never the document, never its contents** — and gets
back a signed statement that this hash existed at that moment.

**Why you want it.** A signature proves *who*. It does not prove *when*: the
signing computer's clock is whatever the signer says it is. Worse, when your
signing certificate eventually expires, signatures made with it become
questionable — unless a timestamp proves they were made while it was still
valid. A timestamped seal keeps proving itself for years.

| Setting | What it is | Default |
|---|---|---|
| `COMMCHECKER_TSA_URL` | Address of the timestamp authority | `http://timestamp.digicert.com` |
| `COMMCHECKER_TSA_REQUIRED` | Refuse to seal if the timestamp fails | on in production, off in demo |
| `COMMCHECKER_TSA_TIMEOUT` | Seconds to wait | `10` |
| `COMMCHECKER_TSA_USERNAME` | Only if your authority requires an account | — |
| `COMMCHECKER_TSA_PASSWORD` | Only if your authority requires an account | — |

**Free, no account needed:**

- `http://timestamp.digicert.com` (the default)
- `http://timestamp.sectigo.com`
- `http://timestamp.apple.com/ts01`

These are fine and widely trusted. A paid, contractually-backed authority is
worth considering if timestamps ever need to survive a legal challenge.

**To turn timestamping off**, set `COMMCHECKER_TSA_URL=` (empty). The test suite
and offline demos do exactly this.

**`COMMCHECKER_TSA_REQUIRED` is the important one.** With it on, a document that
cannot be timestamped is *not sealed at all* — you get a clear error instead of
a weaker seal you did not know about. It defaults on in production for that
reason. In demo mode it defaults off so a laptop with no internet can still run
the demo.

---

## 3. Trust settings — what counts as trustworthy

These control CommChecker's judgement when *checking* somebody else's seal.
They have nothing to do with signing.

| Setting | What it does | Default |
|---|---|---|
| `COMMCHECKER_TRUST_SYSTEM_ROOTS` | Trust the public authorities your operating system already trusts | on in production |
| `COMMCHECKER_TRUST_ROOTS` | Also trust specific certificates — a `.pem` file, or a folder of them | — |
| `COMMCHECKER_ALLOW_FETCHING` | Check online whether a certificate has been revoked | off |

**In production, turn `COMMCHECKER_TRUST_SYSTEM_ROOTS=1` on.** That is what
makes a real CA-issued seal verify with no further setup: the authority that
issued your certificate is already in your operating system's list.

**If no trust roots are configured at all**, CommChecker does not guess. It
reports the signer's identity as *unevaluated* — a grey "?" rather than a green
tick — and says so in the report. It still checks integrity, which does not
depend on trust.

`COMMCHECKER_ALLOW_FETCHING` requires outbound internet access and makes
verification slower. Turn it on when you need to know that a certificate has not
been revoked since it was issued.

---

## 4. Behaviour and limits

| Setting | What it does | Default |
|---|---|---|
| `COMMCHECKER_MANIFEST_PREVIEWS` | Store a short excerpt of each record in the manifest | `1` (on) |
| `COMMCHECKER_MAX_UPLOAD_MB` | Largest PDF the web service accepts | `25` |

**About previews.** With previews on, a FAIL report can show *"when sealed:
Confirmed for tomorrow at 2 / in this file now: at 5"* — far more persuasive
than two mismatched hashes. The excerpt only duplicates text that is already
printed in the same document, so it leaks nothing new.

Set it to `0` if you want hash-only manifests. Detection still works exactly the
same and still names the changed record; you simply lose the before/after
display.

---

## Checking your work

```bash
python cli.py config
```

```
  mode                     production
  signing certificate      production (.p12 supplied)
  certificate source       file: /etc/commchecker/commlocker-signing.p12
  timestamp authority      http://timestamp.digicert.com
  timestamp required       True
  trust roots              none configured
  trust system roots       True
  revocation checking      False
  manifest previews        True
  max upload mb            25

  Configuration looks usable.
```

If anything is wrong it prints a numbered list of problems in plain English and
exits with an error code — so it also works as a deployment check.

Common problems and what they mean:

| Message | Fix |
|---|---|
| *Production mode needs a real signing certificate* | Set `COMMCHECKER_P12_PATH` or `COMMCHECKER_P12_BASE64` |
| *The signing certificate file was not found* | Wrong path, or the file did not get deployed |
| *Could not open the signing certificate … usual cause is a wrong password* | Check `COMMCHECKER_P12_PASSWORD` |
| *COMMCHECKER_TSA_REQUIRED is on but … URL is empty* | Set a timestamp URL, or turn the requirement off |
| *is not valid base64 text* | The certificate text was truncated when pasted — re-run `base64 -w0` |
