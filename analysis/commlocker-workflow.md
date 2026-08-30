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
            + system notification: "✅ '<name>' created"
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
8. **Count discrepancy to check.** A conversation listed as "574 messages" in All
   Texts opened showing "400 messages" after loading settled. Possibly still
   loading, possibly the "readable" filter from observation 4. Needs confirming —
   on an evidentiary record, a silent shortfall matters.

## 6. Open questions (need source code or further clips)

- Where do Files and filed messages live — device-only, or a server?
- What exactly does `Hashed` cover, and is the hash chained/anchored anywhere?
- What does Export produce, and does it carry the integrity proof?
- Which permissions are requested, and when?
- What are "unreadable" messages, and are they silently dropped?
- Is there an account/auth layer at all?
- What happens to a File's records if the underlying device message is deleted?

## 7. Not yet mapped

- Search · Exports · Settings
- Voicemail / Email / Call record paths
- Manage parties · Select messages · Rename · Export File
- Onboarding, permission prompts, first-run
