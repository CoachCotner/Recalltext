# COMMLOCKER™ — Observed Workflow Map

**Method:** reconstructed from screen recordings of the shipped Android build
(tap indicators enabled). Frame-by-frame; no source code access.
**Recordings analyzed:** 2 (creating a File; filing texts into a File).
**Status:** partial — Exports, Settings, Search, and the All Texts tab are not yet covered.

> Personal data note: the recordings contain real contact names, phone numbers,
> and message bodies. Those are deliberately NOT reproduced in this document and
> the extracted frames are NOT committed to this repository.

---

## 1. Global structure

**Header (persistent)**
- COMMLOCKER™ wordmark
- `+ New` button (top right)
- Two segmented tabs: **My Files** | **All Texts** `<count>`
  - the All Texts badge shows the total conversations ingested from the device

**Bottom navigation (persistent, 4 items)**
- Files · Search · Exports · Settings

**Core noun:** a **File** = a tamper-evident container for communication records.
**Core verb:** *filing* — copying existing device messages into a File.

---

## 2. Flow: Create a File

```
Home (empty state: "No active Files")
  └─ tap [+ New]  →  bottom sheet "New File"
       ├─ TYPE       horizontally scrolling chips:
       │             Real Estate · Legal · Tenant · Business · Family Care ·
       │             Family · Friends · Other · [+]
       ├─ FILE NAME  (placeholder is type-aware, see below)
       ├─ NOTES      (optional)
       └─ [Create File] / [Cancel]
            └─ success modal "File created"
                 ├─ [Open File]  → File detail
                 └─ [Not now]    → Home
            + in-app toast: "✅ '<name>' created"
```

**Type-aware copy** — selecting a type changes the icon, the sheet subtitle, and
the name placeholder:
| Type | Subtitle | Name placeholder |
|---|---|---|
| Real Estate | "a deal, listing, or closing" | "e.g. Alvarez Drive Listing" |
| Business | "a contract or engagement" | "e.g. Q3 Vendor Contract" |

**Home screen after first File exists:** gains a `Find records…` search bar, a row
of stat chips, an "N shown" count, an `Active` filter and a `Priority` sort control.
File cards show a status — a new File reads **"Needs records"**.

---

## 3. Flow: Add records to a File  (the core mechanism)

```
File detail (empty: "No records yet")
  └─ [Add to File]  →  sheet with 4 source types:
       ├─ Texts      "Attach a message conversation from this device"
       ├─ Voicemail  "Record or import a voicemail with transcript"
       ├─ Email      "Import an .eml or .mbox with attachments"
       └─ Call       "Log a call — number, direction, duration"
```

### The Texts path — a 3-step wizard

**STEP 1 of 3 — Choose conversations**
- Search conversations · `Sort: Recent` · `Filters`
- "Showing N of N conversations" · `Select shown`
- Each row: avatar, name, number, message count, last-message preview, `CONTACT` badge
- Multi-select via checkboxes
- `Next: Refine (n)` — disabled until ≥1 selected · `Cancel`

**STEP 2 of 3 — Refine messages**
- "Add each conversation in full, or narrow it to the key messages."
- Per conversation, a choice: **`All N messages`** | **`Pick specific…`**
- `Pick specific…` opens a per-conversation message picker:
  - header: "N selected · N loaded · loading all"
  - Search messages · Filters · `Sort: Newest first`
  - `Loading all…` / `Clear selection`
  - progressive load ("Loading readable messages…" → "132 loaded · loading all")
  - per-message checkboxes; media messages show type and size (e.g. "Video · 10.6 MB")
  - `File N to File` confirms the selection
  - once chosen, Step 2 shows **`1 specific · Edit`** instead of All
- `Next: Confirm` · `Back`

**STEP 3 of 3 — Confirm & file**
- "YOU'RE ABOUT TO FILE" summary per conversation + **Total: N conversations · N messages**
- Explicit disclosure notice:
  > "This files only the messages that exist now. New messages in these
  > conversations will not be added automatically."
- **Choose target File(s)** — checkbox list; a File can receive the batch;
  each shows "N new". (Plural: one batch can be filed to multiple Files.)
- `File batch to N File` → button becomes `Filing…` → completes
- `Back` · `Done`
- Toast on completion: "✅ Current messages from 1 conversation preserved and…"
  / "✅ Filed 1 message to this File"

---

## 3b. All Texts tab  (the device message pool)

Header banner: **"All Device Conversations — Pulled on Launch"** — the app
re-reads the device message store on every launch.

Search bar: "Search conversations, contacts, keywords…"

**Each conversation row:** avatar, contact name or bare number, last-message
preview, number, total message count, `Show all` expander, last-activity
timestamp, and a status control on the right:

| State | Control shown |
|---|---|
| Not yet filed | orange **`File`** button (files it directly) |
| Already filed | green **`Filed <File name>`** badge |

Filed conversations also carry a colored left edge-bar in the list.

**`Show all` expands inline**, showing a loading state and a summary row:
"All N messages · File to add one to a File, Options for everything else"
with a **`View Full`** button.

### Conversation detail view

- Header: contact name, number, live message count, `⋮`
- Persistent instruction banner:
  > "Tap any record for its options, use File to add it straight to a File, or tap
  > the three-dot menu above to select additional records for filing.
  > **One record can go to multiple Files.**"
- `Message order` · `Sort: Oldest first / Newest first`
- Loads progressively: "Loading messages… CommLocker is loading this conversation
  from the device." (count climbs 0 → 400 while loading)
- **Per-message row:** direction label (`Me — This device` / party), body,
  metadata (`Owner +…5957 · To +…8840 · Line +…`), timestamp, and controls:
  **`Hashed`** · **`File`** · **`⋮ Options`**
- **Per-message `Options` menu:** Add to File · Add note · Copy text ·
  **Set display name**

### Key architectural finding

Messages show **`Hashed`** in this view — *before* they have been filed into any
File. Hashing therefore happens on ingestion from the device, not at filing time.
In the File view messages show `Hashed` **+ `Filed``; here they show `Hashed` +
an actionable `File` button. The two badges are independent states:

```
device message ──pulled on launch──> Hashed ──filed into a File──> Hashed + Filed
```

This matters for the evidentiary claim: the hash is taken at first sight of the
message, which is the stronger design — but it also means the app is hashing all
1,797 conversations, not only the ones the user chooses to file.


---

## 3c. Flow: Add a Call to a File

`Add to File` → **Call** → "Add Call to File"

- Instruction: "Tap File Here to add an imported call to this file."
- `Search calls by name or number` · `Filter`
- Calls are grouped by party — e.g. "CALLS WITH <NAME>"
- **Per-call row:** direction · party name, date and time, number, and a green
  source label **`Device call log`**, with a **`File Here`** button on the right
  (one tap files it — no wizard for calls)
- Directions observed: `inbound` · `missed` · `no-answer` · `rejected`
- Footer controls: **`Show N more`** (paged list) · **`↻ Refresh from device`** ·
  **`Log a call by hand`** (collapsed disclosure) · `Cancel`

Note the contrast with texts: messages are "Pulled on Launch", calls have an
explicit manual **Refresh from device**.

**Filed calls appear in the File** alongside messages, carrying the same
`Hashed` + `Filed` badges, the source label `Device call log`, and duration
(shown in raw seconds, e.g. "Inbound · 347s").

## 3d. Flow: Add a Note to a record

Record `⋮ Options` → **Add note**

- The sheet shows the record being annotated (number, timestamp, source label)
- `YOUR NOTE` free-text field
- Standing disclosure, with a shield icon:
  > "Notes are your own added context. They are labelled as user-added in every
  > export, and the original record is never changed."
- `Save Note` → toast "Note saved"

**This matches the export.** The PDF's chain-of-custody page states "Notes are
labeled separately and do not alter original communication content." The in-app
promise and the exported document say the same thing — the separation between
evidence and commentary is enforced end to end, not just claimed on one screen.


---

## 4. File detail view (populated)

- Header: back · type icon · File name · export icon · overflow `⋮`
- View toggle: **By Date** | **By Party**
- `Collapse all` · `Sort: Newest first`
- Party filter chips: `All parties` + one chip per party added
- Per-party header card: avatar, name, number, `+ Role` tag button, `⋮`, collapse
  - counters by record type: messages `138 of 138` · calls `0` · voicemails `0` · emails `0`
- Per-message row:
  - direction attributed — party name, or **`Me — This device`**
  - body text
  - metadata line: `Sender +…9464 · From +…9464`, or `To +…9464 · Line unknown`
  - **integrity badges: `Hashed` (shield) and `Filed` (check)** ← the tamper-evident claim
  - `⋮ Options`
  - timestamp: "Received: Aug 30, 2026 · 10:25 AM" / "Sent: …"

**Overflow menu `⋮`:** Add to File · Manage parties (badged) · Rename File ·
Select messages · Export File

---

## 4b. Export output  (analyzed from a real exported PDF)

A 6-page US-Letter PDF, ~840 KB, PDF 1.7, DejaVuSans embedded, unencrypted,
no embedded file attachments in this sample (scope had none).
Filename: `CommLocker_<File>_Transaction_Record_<date>_<ExportID>.pdf`

**Page structure**

| Page | Section | Contents |
|---|---|---|
| 1 | Export Summary | Logo, File name, category, Export ID, generated timestamp, exporter name, counts (messages/calls/voicemails/attachments), record scope, date range, packet section list, participant legend |
| 2 | Conversation Timeline | Date separators; per-message card: type, party, numbers, body, timestamp, and the hash block |
| 3 | Attachment Index | "No attachments were available in this export scope." |
| 4 | About This Device | Hardware attestation block (see below) |
| 5 | How To Read The Hashes | Plain-English explainer of every hash and verification state |
| 6 | Chain Of Custody | Verification summary, 6 numbered custody statements, Export Hash |

Every page carries a running header (record type + Export ID), a page title,
`Page N of 6`, the File name and category, and a footer repeating
`Export ID … | Page N of 6`.

### The per-record hash block

Each message in the timeline carries three lines:

```
Ingestion record hash (SHA-256):  <64 hex>   ← taken when first read from device
Current record hash   (SHA-256):  <64 hex>   ← taken when this document was produced
Verification: MATCH
```

Four documented verification states:
- **MATCH** — unchanged since first read
- **MISMATCH** — changed after first read; the record is still shown, and the label is how you know
- **SOURCE MISMATCH** — the copy still on the device no longer matches what was first read
- **ingestion unpinned** — no first-read fingerprint stored, so no comparison is possible

### Hardware attestation (page 4)

The export includes an Android Key Attestation block describing the producing device:

| Field | Example value |
|---|---|
| Signing hardware | Isolated secure processor |
| Bootloader | Locked |
| Device software | Manufacturer-signed, unmodified |
| Device reported by hardware | Google Pixel 10 |
| Android version | 17.0.0 |
| Security patch | 2026-08 |
| Bound to record hash | `<64 hex>` |
| Attestation certificate | `<64 hex>` |

**"Bound to record hash" equals the Export Hash on page 6.** The hardware
attestation is cryptographically tied to this specific document, not merely
attached to it.

Accompanied by an accurate scope statement: the attestation describes the phone
and its software state, and says nothing about whether the communications
themselves are accurate or complete.

### Honesty of the claims

The document repeatedly and correctly limits itself:
- "Whether a record changed after this app first read it. It does not establish
  that the original was accurate, who wrote it, or that nothing is missing."
- "this record makes no claim of completeness"
- Notes are labeled separately and do not alter original communication content

This candor is a strength, not a weakness — an exhibit that overclaims gets
attacked; one that states its own limits survives cross-examination.

### Defects found in the sample export

1. **Header collision, page 1** — "Page 1 of 6" overlaps the orange
   "TAMPER-EVIDENT COMMUNICATION RECORD" label. Visible layout bug on the cover.
2. **Fields truncated with an ellipsis** rather than wrapped:
   - cover date range → "Aug 27, 2026 - Aug 29,…"
   - participant legend → "Lauren Cotner | Device owne…"
   - every message metadata line → "Device line: un…"
   On an exhibit, a visibly cut-off sentence invites a challenge.
3. **PDF document metadata is empty** — Title, Author, Producer, CreationDate
   all blank. Should carry the File name, exporter, product, and timestamp;
   e-discovery tooling reads these.
4. **No Bates numbering.** `Page N of 6` plus Export ID is good practice but is
   not Bates. The named competitor ships it.
5. **Packet section list is incomplete** — the cover lists 4 sections
   (Cover, Timeline, Attachment Index, Chain of Custody) but the document has 6;
   "About This Device" and "How To Read The Hashes" are missing from the list.


---

## 4a. Home dashboard and File lifecycle

Stat chips across the top are a **status pipeline**, not just counters:

| Active | Review | Ready | Archive |
|---|---|---|---|

File cards show the type icon, name, category, last-activity date, a content
summary ("1 conv · 2 msg · 0 phone…"), and a status word (`Needs records`,
`Ready`). Each card has a document button and a `…` overflow:

**File card overflow:** Edit details · Manage parties · Export · Close file · **Delete**

## 4c. Review & Export screen  (the in-app export flow)

Reached from the File card `…` → Export, or the File detail export icon.

### 1. Readiness checklist
A gated pre-flight with a progress bar:

> **Ready to export** — All readiness checks are complete.
> ✅ Records filed  ✅ Parties labeled  ✅ Exporter identity set

### 2. Export scope
> "Beginning and End define which filed records are included.
> **Your selections are saved for future exports** and can be changed or reset at any time."

`BEGINNING: First record (start of the File)` → `END: Present (through today)`

Tapping either opens **Set Beginning / End of Record**:
- `Oldest` / `Newest` toggle · `Jump to` dropdown
- Records grouped by month heading, each typed (`TEXT`, call, voicemail, email),
  showing party, preview, and timestamp, with a radio selector
- "Choose the first record to include — a text, call, voicemail, or email."

Then: **"N records in scope"** with a per-type breakdown (messages · calls ·
voicemails · attachments).

### 3. Include — packaging mode
`Whole` · `By Party` · `By Role` · `Archive`
("Everything in the range above, in one record.")

### 4. Live preview
The actual rendered cover page is shown inline, so the user sees the real
document before generating it.

### 5. Format and generate
`PDF record` | `+ attachments (ZIP)` → **Export**, captioned with the effective
scope ("All filed records → Present").

### Risk worth flagging

Export scope **persists between exports**. A user who once narrowed a range and
later exports again gets the old narrowing silently applied. The mitigation is
the cover page, which prints the date range and scope label — but **that is
exactly the field that truncates** ("Aug 27, 2026 - Aug 29,…", defect 2 in 4b).
The one disclosure that would reveal an under-inclusive export is the one that
gets visually cut off. Fixing the truncation is therefore not cosmetic.


---

## 4d. Settings

### In-app Settings

| Item | Observed value |
|---|---|
| Exporter Identity | Lauren Cotner |
| Appearance | System |
| Permissions | All granted |
| Contact Aliases | 2 aliases |
| Storage | 2 records |
| Backup & Restore | **1 backup** |
| Subscription | **Active** |
| Diagnostics | restricted |
| About | 0.1.29 (33) |

Plus a `Search settings` field.

### Android App info (OS-level)

| Field | Value |
|---|---|
| Package | `com.commlocker` |
| Version | **0.1.29 (33)** — pre-1.0 |
| Installed from | **App Tester** (sideloaded, not Play Store) |
| Permissions | Call logs, Contacts and accounts, … |
| Notifications | **Off** |
| Storage & cache | **292 MB internal** |
| Mobile data used | 0.98 MB since Aug 15 |

### Three questions this raises

1. **292 MB on disk vs "2 records" in Settings.**
   The app's own storage view counts only filed records, but the OS reports
   292 MB used. Something large is on disk — most likely a local cache of the
   1,797 ingested conversations and their attachments. If so, the app holds a
   full copy of the device's message history, which is a materially different
   privacy posture from "we store what you file." Needs source confirmation.

2. **"1 backup" — to where?**
   The export's chain-of-custody page asserts records are "processed locally."
   If Backup & Restore writes off-device, that claim needs qualifying language
   on the exhibit. If it writes a local file, the claim stands. This is the
   single most important thing to reconcile, because it appears as an assertion
   inside a legal document.

3. **"Subscription: Active" implies a server.**
   Billing means an account and network contact of some kind. Only 0.98 MB of
   mobile data since Aug 15 suggests it is light — licensing rather than content
   sync — but "processed locally" and "has a subscription backend" need to be
   stated together and precisely.

### Distribution note

Version 0.1.29, sideloaded via App Tester. Pre-release, no Play Store review
performed, and Play Store data-safety disclosures have not yet been written —
those will need to match whatever the answers to the three questions above are.


---

## 5. Observations

1. **Device SMS ingestion.** The app reads the device message store wholesale —
   the demo device showed 1,797 conversations available. This is the largest
   privacy surface in the product and the thing most needing source review.
2. **Snapshot semantics, disclosed.** Filing captures messages as they exist at
   that moment; it does not subscribe to the conversation. The app states this
   plainly at the confirm step — good practice, and a deliberate product decision.
3. **`Hashed` is the integrity claim, and it is applied at ingestion.** Every
   message shows a hash badge even before filing (see 3b). *What* is hashed, with
   what algorithm, and whether it is chained or anchored anywhere is not
   observable from the UI. This is the central question for any evidentiary claim.
4. **Progressive loading at scale.** A 1,124-message conversation loads
   incrementally ("Loading readable messages…"). "Readable" implies some messages
   are not — unclear which, or whether the user is told.
5. **Parties are first-class**, with roles and per-type record counters — the data
   model is party-centric, not just chronological.
6. **Records are many-to-many with Files.** Stated explicitly in the UI: "One
   record can go to multiple Files." A message is referenced by Files, not owned
   by one.
7. **Two routes to filing.** The 3-step wizard (bulk, from inside a File) and the
   direct `File` button (single record or whole conversation, from All Texts).
   Both reach the same end state.
8. **Notes are structurally separated from evidence** — user commentary never
   mutates a record, and is labeled as user-added wherever it appears. The UI
   and the export agree on this.
9. **Call durations are shown in raw seconds** ("347s") in the File view. Human
   readers, including attorneys, read "5m 47s" faster. Cosmetic, but it appears
   on an evidentiary record.
10. **Count discrepancy to check.** A conversation listed as "574 messages" in All
   Texts opened showing "400 messages" after loading settled. Possibly still
   loading, possibly the "readable" filter from observation 4. Needs confirming —
   on an evidentiary record, a silent shortfall matters.

## 6. Open questions (need source code or further clips)

- What accounts for 292 MB of local storage when Settings reports 2 records?
- Where does Backup & Restore write, and does it leave the device?
- What does the Subscription check contact, and what does it transmit?
- What exactly is fed into the SHA-256 — body only, or body + metadata + timestamps?
  Is the ingestion hash stored anywhere tamper-resistant, or in the same local
  database as the record it protects?
- Are ingestion hashes chained or externally timestamped? Without that, a
  device-local hash pair proves internal consistency, not third-party custody.
- Which permissions are requested, and when?
- What are "unreadable" messages, and are they silently dropped?
- Is there an account/auth layer at all?
- What happens to a File's records if the underlying device message is deleted?

## 7. Not yet mapped

- Search · the Exports tab in the bottom nav
- Settings sub-screens: Exporter Identity, Permissions, Contact Aliases,
  Storage, Backup & Restore, Subscription, Diagnostics
- Voicemail / Email record paths
- Manage parties · Select messages · Rename · Close file · Edit details
- The `By Party` / `By Role` / `Archive` packaging modes (only `Whole` observed)
- Onboarding, permission prompts, first-run

---

## 8. Update — 5 September 2026 (one week on)

Re-reviewed from three screen recordings of the same build line. The app has moved
on considerably; this section records only what changed.

### Scale

| | 30 Aug | 5 Sep |
|---|---|---|
| Files | 2 | 4 |
| Device conversations ingested | 1,797 | 1,824 |
| Real exports produced | 1 (6 pages) | 4+ across 3 Files |

Largest export observed: **SHS 1976 Reunion — 133 pages, 49.0 MB.**
Also: garnet apts — 28 pages, 11.4 MB (twice, on 1 Sep and 3 Sep).

### The Exports tab is built

Titled **"Generated Communication Records"**, with the line
*"Open, save, or send a tamper-evident record only when you choose."*

Exports are grouped by File ("garnet apts · 2 exports", with `Open record ›`).
Each export card carries: File name, "Communication Record", date · file size ·
page count, the Export ID, a **share** button and a `⋮` menu. Keeping every
generated record listed with its ID is exactly right for an evidentiary tool —
the producer can say which document they handed over, and when.

### Roles are live

The File detail now groups parties under role headings — a `BUYER 1` section
band with its own `⋮` — and party cards carry role tags (a custom
"money bags" tag was visible). Party chips are colour-coded per party across
the filter row and the message rail.

Per-party counters are more granular than before: messages · **media** ·
calls · voicemails · emails, as separate icon counts (e.g. `1` message,
`68` media, `1` call).

### A second filing path: select messages in place

`⋮` → **Select messages** turns the conversation into a selection surface:
- header becomes `Cancel · N Selected · Clear`
- circular checkmarks on each record
- a green **`Add N to File`** action bar pinned to the bottom

This is faster than the three-step wizard for picking a handful of messages
out of a live conversation, and it reaches the same place.

### The Add to File sheet has much better copy

> "Select Files, then save. **This only adds: nothing already filed is removed.**
> One record can go to multiple Files."

Plus a **Create New File** row that starts a new File and files the selection
into it in one step. The added sentence removes a real ambiguity — a user
choosing Files could previously have believed the selection replaced what was
already filed.

### The file-size problem is now the biggest practical one

At 133 pages / 49.0 MB, an export runs about **377 KB per page** — because every
page is a full-page raster (section 4b, and the raster finding below). The same
document emitted as vector text would be on the order of 1–3 MB.

Consequences that are no longer theoretical:
- **49 MB will not go through most email.** The common attachment ceiling is
  25 MB; this is double it.
- Many court e-filing portals impose per-document size caps in the same range.
- The user hit this directly: a 75 MB file could not be uploaded and had to be
  split into three parts.

A record that cannot be sent is not a deliverable. This moves "stop rendering
pages to images" from a correctness issue to a shipping blocker.

### Unchanged

The `Hashed` / `Filed` two-state model, the party-centric data model, the
snapshot semantics and the many-to-many record-to-File relationship all behave
as documented above. Unfiled records show `Hashed` plus an actionable `File`
button; filed records show `Hashed` + `Filed`.

