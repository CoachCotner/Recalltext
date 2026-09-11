# CommLocker v2 — developer handoff

For the Kotlin/Android build. This is the spec behind the clickable mockup in `v2/index.html`. The mockup is the reference for layout and copy; this file is the reference for behavior, data and acceptance. Where the two disagree, this file wins.

- Mockup (live): https://claude.ai/code/artifact/bf93e84c-06e0-4471-ad9d-4fde737d38c8 — tap **Show me** for the seven-step tour
- Walkthrough with captures: `v2/walkthrough.html`
- Target: portrait phone, 9:19.5 aspect (720 × 1560 class). Every screen, including Export, fits one screen height without scrolling at 360 × 780 dp. Lists scroll; pages do not.

## 1. What changes, in one paragraph

One screen replaces Home tabs, the transaction detail screen, Add Call Log, Add Voicemail, Add Conversations and the File-this-message picker. The screen is a list of every conversation on the phone (texts, calls and voicemails together, one row per contact, newest first) with a fixed block of folder chips along the bottom. Each row has a ⋯ menu with two actions: **Add to folder…** and **Export this conversation…**. Tapping a folder chip shows that folder as a date-ordered timeline across all contacts, with **Export…** in its header. Hashing happens at ingestion and is never touched by filing.

## 2. Data model

Keep whatever the ingestion layer already stores. The change is that texts, calls and voicemails become one item type with folder tags, and folders become labels rather than containers.

```kotlin
enum class ItemType { TEXT, CALL, VOICEMAIL }
enum class Direction { IN, OUT }

data class Item(
    val id: String,                 // stable, assigned at ingestion
    val contactId: String,
    val type: ItemType,
    val direction: Direction,
    val timestamp: Instant,         // carrier/device timestamp, never edited
    val body: String?,              // text body, or voicemail transcript
    val durationSec: Int?,          // calls, voicemails
    val missed: Boolean,            // calls
    val attachments: List<Attachment>,
    val note: String?,              // agent note, shown as agent-added, excluded from the record hash
    val ingestionHash: String,      // SHA-256 hex over canonicalBytes, computed once at ingestion
    val canonicalBytes: ByteArray,  // the exact bytes that were hashed, stored verbatim
    val folderIds: Set<String>      // labels; empty = "not filed yet"
)

data class Attachment(val id: String, val kind: String /* image|video|pdf|audio|text */, val fileName: String, val caption: String?, val sha256: String, val bytesRef: String)

data class Contact(val id: String, val displayName: String, val userLabel: String?, val carrierNumber: String, val role: String?, val isUnknown: Boolean, val isSpam: Boolean)

data class Folder(val id: String, val name: String, val icon: String, val category: String?, val note: String?)
```

Rules:

- `ingestionHash` and `canonicalBytes` are written once and never updated. `note`, `folderIds`, `userLabel` live outside the hashed bytes.
- Filing = add a folder id to `Item.folderIds`. Unfiling = remove it. Nothing else changes.
- A conversation's "folders" chips are the union of its items' `folderIds`.
- "Not filed yet" = a contact whose items all have empty `folderIds`.

## 3. Screens and behavior

### 3.1 Everything (home)

- Header: CommLocker mark and wordmark (orange COMM, white LOCKER; the tagline appears on the printed cover sheet, not in the header), a round theme button that cycles System → Light → Dark on each tap (persisted, toast names the new theme), **Show me** tour button (optional in production).
- Title "Everything · N conversations · M items", search field, filter chips: All, Texts, Calls, Voicemails, Not filed yet (each with a count).
- Row per contact: avatar, name, role · number, latest item with a type chip (Text / Call / No answer / Voicemail) and preview, counts by type, lock chip "N hashed", folder chips or "not filed", a **⋯** button. Spam rows dimmed.
- Tap row → expands in place: date dividers, texts as bubbles, calls and voicemails as cards, each with `hashed at ingestion <time> · sha256:<16 hex>…`, attachments as chips, agent note in an amber strip, folder chips. Header line of the thread has **Pick messages**.
- Bottom: fixed 3-column grid of folder chips: **All**, one chip per folder (icon · name · item count, name truncates), **+ New folder**. Never scrolls sideways. Tap a chip → open that folder. Tap the open chip again → back to Everything.

### 3.2 ⋯ menu

- **Add to folder…** → opens the conversation in pick mode with every item ticked, scrolls the row to the top, toast "Everything is ticked. Untick what should stay out, then File picked."
- **Export this conversation…** → Export page (3.5) with scope = this conversation.
- **Open / Collapse conversation**.

### 3.3 Pick mode (inside a conversation)

- Checkbox on every item; tap anywhere on the item to toggle. **All** / **None** in the thread header. **Cancel picking** exits and clears.
- Sticky bar at the bottom of the thread: "K of N picked", **File picked to folder(s)…**, **Done**.
- **File picked** opens the folder popover: title "File K items from <name> to", subtitle "Tap as many folders as you like. Tap again to remove.", one row per folder with a check mark showing whether *all* picked items are already in it, a **New folder name** field with **Create & file**, and **Done**. Tapping a folder files or unfiles the picked set immediately (toast) and leaves the popover open.

### 3.4 Folder view (timeline)

- Top: orange **Back to all conversations**, banner with icon, name, "C contacts · T texts · K calls · V voicemails", **Export…**. Segmented control: **Timeline · everyone, by date** (default) / **By person**.
- Timeline: every item with that folder id, all contacts, sorted by timestamp, date dividers, each item prefixed with avatar + "Name · role" (or "Lauren → Name" for outbound).
- By person: the Everything rows filtered to contacts with items in the folder; each thread shows only that folder's items plus "n more in this conversation not filed here · show faded".
- Filter chips and search apply within the folder.

### 3.5 Export page (one screen, no scroll at 360 × 780)

Top to bottom, in this order:

1. Header: **Back**, "Export", "<scope name> · N records".
2. Three readiness rows: **Records verified** (N of N · MATCH), **Parties labeled** (names) or a warning "K numbers not labeled · carrier number is kept" with an inline name field + Save per number, **Exporter set** (name · license).
3. Scope line: "First record <date> → today", Export ID right-aligned.
4. Four tiles: texts, calls, voicemails, files.
5. **Matching hash · every record** box: "N of N: ingestion hash = current hash → MATCH" and one line of explanation. If any record does not match, this box turns red, says how many, and the Export button is disabled until the user acknowledges (see 4.3).
6. **Export hash** box: 64-hex value, "Over every record hash + Export ID, <timestamp>".
7. Segmented toggles: **PDF record** / **+ ZIP · F files** (ZIP disabled when F = 0). One line under it: "P photos · V videos · D documents · A voicemail recordings · T transcripts, each with its own SHA-256 in the attachment index".
8. Spacer, then a full-width **Export PDF + ZIP** button and a **Preview cover sheet** button.

**Preview cover sheet** is its own page (Back returns to Export). It renders the first page of the PDF and the first two timeline entries exactly as they print, then the attachment index and chain of custody with the export hash.

Export ID format: `CL-<CONV|FOLDER>-<8 hex>` in the mockup; keep the production format `RT-YYYYMMDD-XXXXXXXX` if you prefer, it is not user-facing logic.

### 3.6 New folder

- From the bottom block: **+ New folder** → small popover with a name field and **Create**. Creates and opens the folder.
- From the filing popover: name field + **Create & file** creates the folder and files the picked set in one action.
- Category, icon and notes are optional edits later; not required to create.

## 4. Hashing and the PDF (this is the product)

### 4.1 What to hash, once

At ingestion build one canonical byte string per item and hash it. Store both the hash and the bytes. Suggested canonical form (UTF-8, `\n` separated, no trailing newline):

```
v1
type=<TEXT|CALL|VOICEMAIL>
direction=<IN|OUT>
ts=<ISO-8601 UTC, e.g. 2026-03-21T18:14:00Z>
counterparty=<E.164, e.g. +13105550841>
device_line=<E.164>
body=<text body or transcript, verbatim, or empty>
duration=<seconds or empty>
attachments=<sha256,sha256,... in the order received, or empty>
```

Everything the user can change later (display name, role, notes, folders, category) stays out of this string.

### 4.2 What to print under every record

```
Ingestion SHA-256: <stored hash>
Current SHA-256:   <sha256(stored canonicalBytes) recomputed at export>
Verification:      MATCH | MISMATCH
```

The current hash is recomputed over the **stored bytes**, not over a re-serialized object. That is the whole point of storing `canonicalBytes`: a phone-number normalization change, a timezone change, or a new field in the model must never turn a MATCH into a MISMATCH.

### 4.3 Known defect in the current build

`CommLocker_811_Amapola_no_6_Transaction_Record_20260707_11pgs.pdf` prints **MISMATCH on all 39 records**, while `CommLocker_Debt_collectors_Conversation_Export_20260721` prints MATCH on all 8. In the Amapola export the counterparty number appears in two formats within the same thread (`4245580981` and `+14245580981`), which points at the export re-hashing a re-serialized record after a normalization change. Two things to do:

1. Fix the cause per 4.1 and 4.2 (hash stored bytes; never re-serialize to verify).
2. Never let an export go out quietly with MISMATCH. The readiness row must go red, the Export button must disable, and the cover sheet must carry a visible notice if the user overrides. A record that says MISMATCH 39 times is worse than no record.

### 4.4 Export hash

`sha256( concat(ingestionHash_1 … ingestionHash_N in timeline order) + "|" + exportId + "|" + generatedAtUtc )`. Print it in the chain-of-custody section and in the PDF metadata. Recomputing it from the PDF's own timeline must reproduce it.

### 4.5 ZIP

One ZIP per export, next to the PDF, containing every attachment in scope: images, videos, documents, voicemail audio, voicemail transcript `.txt`. File names as in the attachment index; each entry's SHA-256 is listed in the index and in the ZIP's own manifest (`manifest.json`: file name, kind, sha256, source item id, timestamp). Voicemail audio comes from the visual-voicemail store where the device exposes it; if it does not, include the transcript and say so in the index.

### 4.6 PDF structure (keep what exists)

Cover / Export Summary → Conversation Timeline (both hashes per record) → Attachment Index → Chain of Custody with Export Hash. This is the current generator's structure; keep it, just add the "Current SHA-256" line where it is missing and the MISMATCH handling.

## 5. Palette and type (locked)

Logo palette: Navy `#071B42`, Burnt orange `#B95722`, Secondary burnt orange `#C56230`, Beige `#F4F1EC`, Soft white `#EDEDED`. Website palette is managed separately; the app uses the mapping below and nothing else.

| Token | Light | Dark | Used for |
|---|---|---|---|
| ground | `#F4F1EC` | `#01173C` | screen background |
| card | `#FFFFFF` | `#071B42` | rows, sheets, popovers |
| header | `#071B42` | `#01173C` | top bar, tour card, selected filter chip |
| text | `#111C32` | `#EDEDED` | body text |
| muted | `#515D71` | `#EDEDED` @ 58% | secondary text, timestamps |
| divider | `#2B4169` @ 22% | `#2B4169` | borders and lines |
| button | `#C56230` | `#C56230` | primary buttons, selected folder, "on" states |
| button hover/pressed | `#E8793A` | `#E8793A` | |
| eyebrow | `#B95722` | `#E8793A` | small uppercase labels, agent-note strip, "no answer" |
| success | `#16A34A` | `#4ADE80` | verified rows, MATCH, voicemail cards |
| wordmark | COMM `#B95722` · LOCKER `#EDEDED` on the header; LOCKER `#071B42` on paper (cover sheet) | | |

Two status colors sit outside the palette on purpose, because they must not read as brand: texts `#2B4169` (navy, in palette) and calls `#0F766E` (teal). Swap the teal if you have a house choice; keep it distinct from orange and green.

Type: Plus Jakarta Sans 400–800 for the UI, Michroma for the wordmark only. Body 14 sp, row title 14 sp bold, chips 11–12 sp bold, hashes 10 sp monospace.

## 6. Acceptance checklist

- [ ] At 360 × 780 dp the Everything list, an open folder, the pick bar and the Export page each fit the screen; only lists scroll.
- [ ] Folder chips: all visible in a fixed 3-column block; no horizontal scrolling.
- [ ] ⋯ → Add to folder opens with 100% of items ticked; the count reads "N of N picked".
- [ ] Unticking two items and filing puts N-2 items in the folder; the two remain "not filed" (or in their other folders).
- [ ] The folder popover stays open after a tap; the same picked set can be filed to two folders in a row; Done closes it.
- [ ] Typing a new folder name in the popover creates the folder and files the set in one action.
- [ ] Tapping a folder chip opens the timeline with items from all contacts in date order; tapping it again returns to Everything; the orange Back button does the same.
- [ ] Export readiness: an unknown number blocks with an inline name field; saving the name keeps the carrier number and unblocks.
- [ ] Every record in the PDF prints ingestion hash, current hash and MATCH. A deliberately altered stored byte string produces MISMATCH, turns the readiness row red and disables Export.
- [ ] The export hash printed in the PDF equals the value recomputed from the PDF's timeline hashes + Export ID + generated time.
- [ ] ZIP contains every attachment in scope with names and SHA-256 matching the attachment index.
- [ ] Filing, unfiling, renaming a contact and adding a note never change any ingestion hash.
- [ ] Theme button cycles System, Light, Dark; the choice survives an app restart; every screen is readable in both themes.

## 7. Out of scope for this pass

Multi-select across rows, drag and drop, category templates on folder creation, the incoming-call capture demo. All can come later without touching the data model above.
