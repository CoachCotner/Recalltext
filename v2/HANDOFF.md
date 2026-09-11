# CommLocker v2 — developer handoff

For the Kotlin/Android build. This is the spec behind the clickable mockup in `v2/index.html`. The mockup is the reference for layout and copy; this file is the reference for behavior, data and acceptance. Where the two disagree, this file wins.

- Mockup (live): https://claude.ai/code/artifact/bf93e84c-06e0-4471-ad9d-4fde737d38c8 — tap **Show me** for the seven-step tour
- Walkthrough with captures: `v2/walkthrough.html`
- Target: portrait phone, 9:19.5 aspect (720 × 1560 class). Every screen, including Export, fits one screen height without scrolling at 360 × 780 dp. Lists scroll; pages do not.

## 0. What the current build (0.1.29, Android) already has, and what happens to it

From the screenshots of the shipped app:

| Today | In the redesign |
|---|---|
| Header with the COMMLOCKER wordmark, **+ New** | Same wordmark (the header asset, unchanged), theme button, Settings gear, tour |
| **My Files / All Texts** tabs, "Find records…" | One list, "Everything on this phone", with unit-labeled filter chips |
| File card ⋯: Edit details, Manage parties, Export, Close file, Delete | Folder ⋯ (in the folder header and the Folders sheet): Rename, Export, Delete. "Close file" becomes an optional archive flag later; "Manage parties" is the × on chips plus labeling in the export checks |
| **Add to File** sheet: Texts / Voicemail / Email / Call pickers, each its own screen | Gone. Everything is already in the list; ⋯ → Add to folder picks from it |
| **Add Voicemail to File** with "Add a voicemail by hand" | Gone. Voicemails sit in the list. Keep the **Refresh from device** action in Settings › Storage |
| Bottom nav: Files, Search, Exports, Settings | No bottom bar (it cost list space). Search is the field at the top; Exports and Settings are behind the gear |
| **Exports** tab: Generated Communication Records with date, MB, pages, `CL-YYYYMMDD-XXXXXXXX`, share | Same list under Settings › Exports; the mockup uses your ID format |
| Settings: Exporter Identity, Appearance, Permissions, Contact Aliases, Storage, Backup & Restore, Subscription, Diagnostics, About | All kept as they are, reached from the gear. Appearance gains System / Light / Dark as one-tap chips |
| Permissions: READ_SMS, READ_CONTACTS, READ_CALL_LOG, PHONE LINE, RCS notification access, Import Email (.eml / .mbox), Import Call Logs Now | Unchanged. .eml/.mbox import is how emails enter the list |

Two facts from the screenshots that change assumptions elsewhere in this file: the app is **Android** (App info screen), and the device voicemail rows say **"No provider transcript exposed"**, so a voicemail item must render with audio and an optional user note when no transcript exists. The export sheet's "voicemail recordings" count covers that case.

## 1. What changes, in one paragraph

One screen replaces Home tabs, the transaction detail screen, Add Call Log, Add Voicemail, Add Conversations and the File-this-message picker. The screen is a list of every conversation on the phone (texts, calls, voicemails and emails together, one row per contact, newest first) with a fixed block of folder chips along the bottom. Each row has a ⋯ menu with two actions: **Add to folder…** and **Export this conversation…**. Tapping a folder chip shows that folder as a date-ordered timeline across all contacts, with **Export…** in its header. Hashing happens at ingestion and is never touched by filing.

## 2. Data model

Keep whatever the ingestion layer already stores. The change is that texts, calls and voicemails become one item type with folder tags, and folders become labels rather than containers.

```kotlin
enum class ItemType { TEXT, CALL, VOICEMAIL, EMAIL }
enum class Direction { IN, OUT }

data class Item(
    val id: String,                 // stable, assigned at ingestion
    val contactId: String,
    val type: ItemType,
    val direction: Direction,
    val timestamp: Instant,         // carrier/device timestamp, never edited
    val body: String?,              // text body, voicemail transcript, or email body (plain text)
    val subject: String?,           // email only
    val fromAddress: String?,       // email only
    val toAddresses: List<String>?, // email only
    val messageId: String?,         // email only, RFC 5322 Message-ID, part of the canonical bytes
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

- Header: CommLocker wordmark only, no mark: COMM orange, L white, O orange, CKER white, ™ (the tagline appears on the printed cover sheet, not in the header), a round theme button that cycles System → Light → Dark on each tap (persisted, toast names the new theme), **Show me** tour button (optional in production).
- Title "Everything on this phone · N people · M items", search field, filter chips that carry their unit so nothing is ambiguous: "117 items", "99 texts", "10 calls", "2 voicemails", "6 emails", "12 people not filed yet". The type chips count items and sum to the total. "People not filed yet" counts contacts (spam excluded) with nothing in any folder.
- Row per contact: avatar, name, role · number, latest item with a type chip (Text / Call / No answer / Voicemail / Email) and preview, counts by type, lock chip "N hashed", folder chips or "not filed", a **⋯** button. Spam rows dimmed.
- Every folder chip, on a row and on an item, carries an **×**. On a row it takes that whole conversation out of the folder; on an item it takes only that item out. Toast confirms. Nothing is deleted; the label is removed.
- Tap row → expands in place: date dividers, texts as bubbles, calls and voicemails as cards, each with `hashed at ingestion <time> · sha256:<16 hex>…`, attachments as chips, agent note in an amber strip, folder chips. Header line of the thread has **Pick messages**.
- Bottom: a **two-row** block of folder pills. Pills size to their text, left-justified, wrapping; a folder name is capped at **35 characters** with an ellipsis on the pill (the full name is in the tooltip and everywhere else). Order: **All**, the open folder first, then folders in creation order, then **+ New folder**. As many pills as fit in two rows are shown; the rest collapse into **All N folders ▸**, which opens the Folders sheet. The open folder is never hidden. Larger system fonts grow the pills, not the row count. The label row has a **manage** link. Tap a pill → open that folder. Tap the open pill again → back.
- Folder chips on rows and items follow the same 35-character cap.
- The list is sorted by each person's most recent item, newest first; spam sinks to the bottom. Inside a conversation and inside a folder timeline, items run oldest to newest with date dividers, the way a record reads.

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
3. Date-range row (tappable): calendar icon, "All dates ▾ · N of N records" or "Mar 11 – Apr 10 ▾ · k of N records", Export ID right-aligned. Tapping opens the same date popover as the list (3.9); the export rebuilds with the new range.
4. Five tiles: texts, calls, voicemails, emails, files.
5. **Matching hash · every record** box: "N of N: ingestion hash = current hash → MATCH" and one line of explanation. If any record does not match, this box turns red, says how many, and the Export button is disabled until the user acknowledges (see 4.3).
6. **Export hash** box: 64-hex value, "Over every record hash + Export ID, <timestamp>".
7. Segmented toggles: **PDF record** / **+ ZIP · F files** (ZIP disabled when F = 0). One line under it: "P photos · V videos · D documents · A voicemail recordings · T transcripts, each with its own SHA-256 in the attachment index".
8. Spacer, then a full-width **Export PDF + ZIP** button and a **Preview cover sheet** button. **Export** opens a destination menu inside the frame: **Save on this phone** (Downloads › CommLocker › <Export ID>), **Google Drive**, **Dropbox**, **Email it**, **More…** (the Android share sheet). PDF and ZIP travel together to the chosen destination.

**Preview cover sheet** is its own page (Back returns to Export). It renders the first page of the PDF and the first two timeline entries exactly as they print, then the attachment index and chain of custody with the export hash.

Export ID format: `CL-YYYYMMDD-XXXXXXXX`, the same as the current build's Exports list.

### 3.6 Folders sheet (manage)

Opened from **manage** in the folder block, from **All N folders ▸**, or from the ⋯ in an open folder's header. Full-screen page with Back.

- Top: **New folder name** + Create.
- One row per folder: icon, name, "C contacts · N items", **Open**, **⋯**. The ⋯ expands an inline action row: **Rename** (inline field, Save, Cancel), **Export…**, **Delete**.
- **Delete** asks inline: "Delete “X”? Its N items stay in Everything and in any other folder. Only this label goes." then **Delete folder** / Cancel. Deleting removes the folder id from every item and never touches an item, a hash or an attachment. Temporary folders made for a one-off export are deleted this way.
- Footer: note that folders and filing are stored on the device, and **Reset sample data** (mockup only).

### 3.7 Permissions that fix themselves

Settings › Permissions never just says "All granted". Each permission is a row with what it does in plain words and a status: **Granted**, or **Needs attention** highlighted in orange with a **Fix** button. Fix opens the exact Android screen for that permission, with the path printed under it, for example RCS: `Settings › Notifications › Notification access › CommLocker`. The row explains: "Tap Fix. On the screen that opens, turn on CommLocker, then come back. We re-check the moment you return." When anything is missing, the Everything list shows a one-line orange banner at the top, "RCS messages not being captured · Fix", so nobody has to go looking, and the Settings row reads "1 needs attention".

Implementation: re-check on every `onResume`. Deep links: runtime permissions → `ACTION_APPLICATION_DETAILS_SETTINGS` for the package; RCS notification access → `ACTION_NOTIFICATION_LISTENER_SETTINGS` (Android 11+: `ACTION_NOTIFICATION_LISTENER_DETAIL_SETTINGS` with the component); visual voicemail → the carrier app or `ACTION_APPLICATION_DETAILS_SETTINGS`. If a deep link is unavailable on a device, fall back to App info and keep the printed path visible.

### 3.8 New folder

- From the bottom block: **+ New folder** → small popover with a name field and **Create**. Creates and opens the folder.
- From the filing popover: name field + **Create & file** creates the folder and files the picked set in one action.
- Category, icon and notes are optional edits later; not required to create.

### 3.9 Date range (list, folders and export)

One filter, stored once, applied everywhere: `DateRange(from: Long?, to: Long?)` in the list ViewModel, compared against the item's ingestion timestamp. Everything that reads items (the Everything list, the filter-chip counts, an open folder, the timeline, pick mode) goes through the same query, so the counts always agree with the rows.

- Control: a **calendar button** at the right end of the search field reads "All dates"; when a range is active it turns orange, reads "Mar 11 – Apr 10" (year only when it differs from the current year), and an **×** next to it clears the range.
- Tapping it opens a popover with four presets, each with its item count (**All dates**, **Last 30 days**, **Last 90 days**, **This year**), and **From / To** fields with **Apply**. In Kotlin use `MaterialDatePicker.Builder.dateRangePicker()` for the custom range; the presets are one-line arithmetic. "From" after "To" is refused inline.
- Room: `WHERE (:from IS NULL OR ts >= :from) AND (:to IS NULL OR ts <= :to)`, with `to` set to 23:59:59.999 of the chosen day. Index `ts`.
- A contact with no items inside the range drops out of the list; the count line reads "N people · M items" for the range. Search matches only inside the range too.
- Export starts from the range active on the list, and can change it on the Export page without leaving it (3.5, step 3). The cover sheet prints "Scope: … · limited to <from> – <to>" and the "Date range" line shows the first and last record actually included. The export hash covers only the included records, so a date-limited export has its own hash and its own Export ID.

### 3.10 Export several people separately (batch)

Not a merged file. The same single export, run once per person, delivered together.

- Entry: ⋯ → **Export with other people…** puts the list in tick mode: a checkbox appears at the left of every row, the ⋯ buttons hide, tapping a row ticks it. A bar above the folder block reads "N people ticked · Cancel · **Export N separately**".
- The Export page header reads "Export separately · N people · N PDFs, one each". Readiness rows are the union (records verified, parties labeled, exporter set). The date-range row applies to every person at once. Then one card per person: name, "k of n records · f files · own PDF + ZIP", its own Export ID and export hash, and an × to leave that person out. Segmented **PDF records** / **+ ZIPs · F files**, then **Export N PDFs + Z ZIPs** and **Preview cover sheets** (tabs across the top switch between people).
- Implementation: `ExportJob(scope, range)` is what already exists. Batch = `ids.map { ExportJob(Scope.Conversation(it), range) }` run sequentially inside one `WorkManager` job with one progress notification. Each job writes `<ExportId>.pdf` (and `.zip` when it has attachments) into the same output folder `Downloads/CommLocker/<yyyy-MM-dd>/`; the destination step shares them with `ACTION_SEND_MULTIPLE` (Drive, Dropbox, Email, More…) or leaves them on the device. Each file gets its own row in Settings › Exports with its own ID, hash and date range.
- Nothing about hashing changes: per-record hashes are the stored ones, the export hash is per file, and no file contains two people's records.

### 3.11 Search

Search matches the contact name, number and role first (listed first), then whole words inside message text, voicemail transcripts, email subjects and call notes. "ace" finds Ace Johnson and the one person whose text mentions "Ace"; it no longer finds "place". A row that is listed only because of a message match shows why: "mentions “ace” in 1 item". The count line reads "N people match “ace”". Room: `MATCH` on an FTS4 table over `body`, joined to contacts; name matches with `LIKE '%q%'`.

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

### 4.5 Email as a record

Emails are items like texts and calls. Sources, in order of preference: the device's mail accounts through the Gmail API or IMAP with the user's consent, and **.eml import** for one-offs (share an .eml to CommLocker). Store subject, from, to, date, plain-text body, Message-ID and attachments. Canonical bytes add three lines: `subject=`, `from=`, `message_id=`. The row and thread show an envelope chip, subject, from/to and the body; attachments go to the ZIP like any other. The PDF prints "Email" as the record type with From/To and Subject above the body, then both hashes.

### 4.6 ZIP

One ZIP per export, next to the PDF, containing every attachment in scope: images, videos, documents, voicemail audio, voicemail transcript `.txt`. File names as in the attachment index; each entry's SHA-256 is listed in the index and in the ZIP's own manifest (`manifest.json`: file name, kind, sha256, source item id, timestamp). Voicemail audio comes from the visual-voicemail store where the device exposes it; if it does not, include the transcript and say so in the index.

### 4.7 PDF structure (keep what exists)

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
- [ ] Filter chips sum: texts + calls + voicemails + emails = items. "People not filed yet" equals the number of non-spam contacts with no item in any folder.
- [ ] × on a row's folder chip removes every item of that contact from that folder; × on an item's chip removes only that item.
- [ ] Folders sheet: create, rename, delete; deleting a folder with N items leaves all N items in Everything with their hashes unchanged.
- [ ] With 15 folders the bottom block is still two rows and the list keeps its height; the open folder is always visible in the block.
- [ ] Every popover and sheet (⋯ menu, folder list, export destinations, Folders sheet, Export page) renders inside the phone frame; nothing extends past its edges.
- [ ] Export destination menu offers this phone, Google Drive, Dropbox, Email, More; PDF and ZIP arrive together at the destination.
- [ ] An imported .eml appears as an Email item with subject, from, to, body and attachments, hashed at import.
- [ ] Folder pills size to their text, capped at 35 characters; the bottom block never exceeds two rows; the open folder is always visible; the rest collapse into "All N folders".
- [ ] Date range: choosing "Last 30 days" changes the rows, the chip counts and the count line together; clearing with × restores all; a contact with nothing in the range disappears from the list.
- [ ] Date-limited export: the PDF contains only records inside the range, prints "limited to <from> – <to>" on the cover sheet, and its export hash differs from the all-dates export of the same person.
- [ ] Batch export of two people produces two PDFs (and a ZIP for each person with attachments), each with its own Export ID and export hash, delivered together to the chosen destination; Settings › Exports lists them as two rows.
- [ ] Search "ace" lists Ace Johnson first and a message-only match with a "mentions" tag; "place" does not match "ace".
- [ ] Revoking RCS notification access shows the banner on the list and "1 needs attention" in Settings; Fix opens the notification-access screen; returning to the app clears both without a restart.

## 7. Out of scope for this pass

Drag and drop, category templates on folder creation, the incoming-call capture demo. All can come later without touching the data model above.
