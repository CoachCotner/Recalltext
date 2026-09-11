# CommLocker Filing Desk — redesign plan

**One screen. What's on your phone, and where it goes.**

Today the app splits a deal across two tabs, a detail screen and four forms, and calls and voicemails sit in a block of their own. The redesign is one phone screen: every text, call and voicemail in one list, folders along the bottom, and a ⋯ on each conversation to file or export.

- Developer handoff (data model, behavior, hashing rules, acceptance checklist): [`v2/HANDOFF.md`](./HANDOFF.md)
- Clickable mockup, sized for a 9:19.5 portrait phone: [`v2/index.html`](./index.html) · live preview: https://claude.ai/code/artifact/bf93e84c-06e0-4471-ad9d-4fde737d38c8 (runs on the app's real sample data; tap **Show me** for a guided walk-through)
- Seven-screen walkthrough with captures: [`v2/walkthrough.html`](./walkthrough.html) · live: https://claude.ai/code/artifact/24840a15-2166-44f8-af48-f918ab4f34ba
- Before/after drawing: [`v2/before-after.svg`](./before-after.svg)

![Today versus redesign](./before-after.svg)

## In plain words

- **A row** is one line in the list: one person or one number, for example the Paul Henderson line. Tap it and it opens to show every text, call and voicemail with that person.
- **Filing a conversation** starts with the **⋯** on its row, then **Add to folder…**. The conversation opens with every text, call and voicemail ticked. Untick what should stay out, tap **File picked**, tick one or more folders or type a new folder name, Done.
- **Filing** is a label, not a copy. It says "these records belong to the 1010 Catalina deal." The message, call log or voicemail is not changed, moved or duplicated. One item can carry several labels.
- **The hash** is stamped earlier than any of this, the moment the item is pulled off the phone. Filing happens after and cannot touch it. Every item in the mockup shows its "hashed at ingestion" line, and the export carries the same hash.

```mermaid
flowchart LR
  P[Your phone<br/>text · call · voicemail] --> I[CommLocker pulls it in]
  I --> H[SHA-256 hash + timestamp<br/>stamped at ingestion]
  H --> E[Appears in Everything<br/>already certified]
  E --> F[You file it to one<br/>or more folders<br/>a label, nothing changes]
  F --> X[Export PDF<br/>carries the original hash]
  classDef key fill:#F4F1EC,stroke:#C56230,color:#B95722
  classDef step fill:#FFFFFF,stroke:#071B42,color:#111C32
  class H key
  class P,I,E,F,X step
```

## Steps, today versus redesign

| You want to… | Today | Redesign |
|---|---|---|
| See one deal's texts, calls and voicemails | **3 taps + scroll.** Home → transaction → scroll past texts to "Phone Records". Calls and voicemails never appear in the By Date view. | **1 tap.** Tap the folder and you get the transaction timeline: everything filed there, from every person, in date order, calls and voicemails inline. "By person" groups the same items by contact. |
| File a text conversation to a deal | **4 taps.** All Texts tab → expand contact → tap 📁 on a message → pick the record. Repeat per message. | **4 taps.** ⋯ → Add to folder… (everything ticked) → File picked → tap the folder. Untick anything that should stay out first. |
| Record a phone call | **3 taps + 7 fields.** Open transaction → scroll → Add Call Log → type name, number, date, duration, direction, notes. | **0 fields.** The call is already in the left stream from the phone's call log. Drag it to a folder. |
| Save a voicemail | **3 taps + 6 fields.** Open transaction → scroll → Add Voicemail → paste transcription and details. | **0 fields.** Voicemail and carrier transcript land in the stream under the caller. File it like anything else. |
| Start a new deal folder | **6 taps + 3 fields.** ＋ New Transaction → name → category → note → Create → Add Conversations → select → Add. | **1 field.** Type a name, press Enter. Or drop a conversation on "New folder" and name it. |
| File only part of a conversation | **4 taps per message.** Expand the contact, tap 📁 on one message, pick the record, close. Repeat. | **Tick, then file once.** Open the conversation, tap Pick messages, tick any mix of texts, calls and voicemails, then File picked. All or None in one tap. |
| Put the same messages in two or more deals | **Per message.** Tag each message separately. | **Tick more folders.** The folder list stays open with check marks; tap as many as apply, then Done. Chips on each item show where it lives. |
| Export a certified record | Transaction → Export → Preview → Download. PDF only. | **⋯ → Export.** From any conversation or any folder. Readiness checks, then one tap for the PDF and a ZIP of every photo, video and voicemail recording. |

## What the left pane shows

- **One row per person or number.** Name, role, number, the latest item with a type chip (Text / Call / Voicemail), counts, and the folders it is filed in. Unknown numbers and spam are in the same list, spam dimmed.
- **Filters instead of tabs.** All · Texts · Calls · Voicemails · Not filed yet. "Not filed yet" is the to-do list.
- **Tap a row to open the thread in place.** Texts as bubbles, calls and voicemails as cards, all on one timeline with date dividers. Each item has its own small File button.
- **Pick messages.** Inside any open conversation, tap Pick messages and checkboxes appear on every text, call and voicemail. Tick what belongs to the deal (or All, then untick the personal ones). A bar at the bottom files the picked set to one or more folders in a single move. Unpicked items stay out of the folder.
- **Inside a folder** the list narrows to what is filed there. Items from the same conversation that are not in the folder hide behind "n more, show faded".
- **The ⋯ menu on every conversation** has two jobs: **Add to folder…** opens the conversation with everything ticked so you choose what goes in, then pick one or more folders or type a new folder name right there. **Export this conversation…** opens the export sheet.

## One thing in the current export to fix first

The two sample exports disagree. The single-conversation export (Debt collectors, 8 records) prints **Verification: MATCH** on every record. The transaction export (811 Amapola no 6, 39 records) prints **Verification: MISMATCH** on every record, and the counterparty number appears in two formats inside the same thread. That points at the export re-hashing a re-serialized record after a phone-number normalization change, rather than re-hashing the bytes stored at ingestion.

Two fixes, both specified in [`v2/HANDOFF.md`](./HANDOFF.md): store the exact canonical bytes hashed at ingestion and verify against those; and never let an export go out quietly with MISMATCH (readiness row red, Export disabled).

## What an export contains

The export sheet mirrors the Review & Export screen and the PDF the current build produces, from any conversation or any folder. Three checks run first: every record verified, every party labeled (an unlabeled number can be named in the sheet, carrier number kept), exporter identity set.

- **Matching hash on every record.** Under each text, call and voicemail the PDF prints the ingestion record hash, the current record hash, and **Verification: MATCH**.
- **Export hash.** One SHA-256 over every record hash plus the Export ID and time, printed in the chain-of-custody section. The fingerprint of the export itself.
- **PDF record.** Cover sheet (file, scope, Export ID, generated, exporter, date range, counts, participants), full timeline, attachment index, chain of custody, export hash.
- **ZIP of attachments.** Every photo, video, document, voicemail recording and transcript in scope, each listed in the attachment index with its own SHA-256.

## Folders along the bottom

- **New folder is one field.** Tap + New folder, type a name, Create. Or type the name inside the filing list and it is created and filed in the same move.
- **Each folder chip** shows its icon, name and item count. Tap to open its timeline; tap again to go back.
- **Getting back out of a folder** is the orange "Back to all conversations" button at the top of the list, or tapping the same folder again.
- **Opening a folder shows the transaction as a timeline.** Every text, call and voicemail filed there, from every person, in one date-ordered stream with the sender named on each item. That is the record you export. Switch to By person to group by contact.
- **Always visible.** The folder chips sit in a fixed block along the bottom, all of them, nothing to scroll sideways.

## Flowchart of the changes

```mermaid
flowchart TD
  A([Today: index.html<br/>2 tabs · detail screen · 4 forms]) --> B
  B[1 · Unify the data<br/>one item list per contact:<br/>texts + calls + voicemails, each with a date and folder tags]
  B --> C[2 · One-screen shell<br/>the list, folders along the bottom<br/>replaces Home tabs and the detail screen]
  C --> D[3 · Thread in place<br/>tap a row, see all three types in date order<br/>calls and voicemails inline]
  D --> E[4 · Filing in one move<br/>⋯ → Add to folder · everything ticked · untick · File picked<br/>multi-folder check marks · new folder in the same box]
  E --> F[5 · New folder = one field<br/>name → Enter · drop onto New folder<br/>category optional later]
  F --> J[6 · Export sheet<br/>readiness checks · matching hash per record · export hash<br/>PDF plus ZIP of photos, videos and voicemails]
  J --> K[7 · Remove the old steps<br/>All Texts tab · Add Call Log form · Add Voicemail form<br/>Add Conversations · File This Message picker]
  K --> L[8 · Live phone data<br/>call log and voicemail feed into the stream automatically<br/>replaces the simulated forms for good]
  L --> M([Done: one screen, one move])
  classDef now fill:#F4F1EC,stroke:#071B42,color:#111C32
  classDef step fill:#FFFFFF,stroke:#071B42,color:#111C32
  classDef key fill:#F4F1EC,stroke:#C56230,color:#B95722
  classDef done fill:#C56230,stroke:#C56230,color:#EDEDED
  class A now
  class B,C,D,F,J,K,L step
  class E key
  class M done
```

## How I would build it

The app is one file, `index.html`, with sample data and screens in the same script. The mockup was built from that file's real data, so this is the mockup's code moved into the app, step by step. Estimates are working days for one developer on the prototype.

1. **Unify the data (1 day).** Texts live in `ALL_CONVS`, calls and voicemails inside each transaction's `extra` list, and the All Texts tab has a third list (`ALL_TEXTS`). Merge into one list of contacts, each with items of type text / call / voicemail, a real timestamp, and a list of folder ids. Match calls and voicemails to contacts by phone number.
2. **One-screen shell (1 day).** Keep the 430px phone frame. One column: header, search and filter chips, the list, and a fixed block of folder chips along the bottom. Replaces `#screen-home`, `#screen-detail`, `.bnav`, `.fab`.
3. **Thread in place (1.5 days).** Reuse the bubble renderer and the call/voicemail cards, rendered from one sorted item list with date dividers, inside the row. Keep notes, attachments, Identify and Beginning of Record on each item. Refactors `renderDetailByDate` + `renderExtraItem` into `renderThread(contact)`; deletes `renderDetailByParty`, `renderFullConv`.
4. **Filing in one move (1.5 days).** The ⋯ menu opens the conversation with everything ticked; File picked opens the folder list with check marks and a new-folder box. Filing adds a folder id to the item and never edits the original. Replaces `openTagPicker`, `openSimpleTagPicker`, `openExtraTagPicker`, `openTextFilePicker`, `openAddConvs`.
5. **New folder is one field (0.5 day).** Name + Enter; drop on New folder creates and files. Category, icon and notes become an optional edit using the existing category grid.
6. **Reconnect export (0.5 day).** Export PDF on a folder builds the input `generatePDF` expects from the items tagged to that folder. Hashes, Beginning of Record and notes unchanged.
7. **Remove the old steps (0.5 day).** Delete `m-call`, `m-vm`, `m-add-convs`, `m-tag`, `switchHomeTab`, `renderAllTexts`, `addCall`, `addVM`. Keep Identify Caller, the annotation sheet and the incoming-call demo.
8. **Live phone data (native app work).** The forms existed only because the prototype can't read a phone. In the shipped app the call log and voicemail feed fill the stream on their own. iOS does not let third-party apps read call history; Android exposes `CallLog` and visual voicemail providers. Confirm with the mobile developer.

**Total for the web prototype:** about 6 to 7 working days, shipped at `recalltext.io/v2` first so the current demo stays untouched.

## What stays and what goes

| Stays | Goes |
|---|---|
| Navy and orange brand, Plus Jakarta Sans | My Transactions / All Texts tabs |
| Certified PDF export with SHA-256 hashes | Separate transaction detail screen |
| Beginning of Record marker | "Phone Records" block at the bottom |
| Agent notes, clearly marked as added | Add Call Log form (7 fields) |
| Identify Caller with carrier metadata preserved | Add Voicemail form (6 fields) |
| Categories and role templates, now optional | Add Conversations multi-select sheet |
| Incoming-call capture demo | File This Message picker |

## Three things to decide

1. **What should dragging a whole row do?** The mockup files every item in that conversation. The alternative is to open it in Pick mode with everything ticked so you can untick before filing. One extra tap, fewer personal messages in deal records. I lean toward the second for contacts who are also friends.
2. **Should "Not filed yet" nag?** A count badge on the filter is quiet. A daily reminder is not. Left quiet.
3. **Where does the pitch site go?** If the two-pane version replaces recalltext.io, the incoming-call demo needs a new home, probably a button in the top bar.
