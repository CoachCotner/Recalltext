# CommLocker v2 — brief for the development team

*From Lauren Cotner. This sits on top of `HANDOFF.md` (the spec) and `PLAN.md` (the reasoning). Read this first.*

## Where we are

You built the app we asked for, and it works: texts, calls and voicemails come off the phone with a hash, folders hold them, the PDF prints with chain of custody. That core is the product and none of it changes.

What we learned from six months of using it, in front of brokers, is about the *shape* of the app, not the engine. The broker who liked it most said one thing: it has to be easier to use. Our own list of blockers on the current build runs to thirty pages, and almost every line traces back to the same three causes:

1. A deal is spread across two tabs, a detail screen and four forms. Texts live in one place, calls and voicemails in another, so nothing reads as one record.
2. Adding to a folder is one message at a time, and calls and voicemails have to be typed in by hand.
3. The app does not tell the user what to do next.

v2 is the answer to those three causes. It is one screen, one menu, and a guided first run. Everything under it (ingestion, hashing, storage, PDF, export ID, exporter identity, permissions, settings) is the code you already wrote.

## What stays exactly as it is

- Ingestion from the phone and the ingestion hash. (One fix, 4.3 in the handoff: verify against the stored canonical bytes, so the Amapola export stops printing MISMATCH.)
- The PDF generator, cover sheet, attachment index, chain of custody, export hash, Export ID format.
- Settings: exporter identity, appearance, permissions, aliases, storage, backup, subscription, diagnostics, about.
- Room, the tables, the Kotlin architecture. v2 adds columns and one view; it does not replace anything.

## What changes, in three iterations

**Iteration 1 · one list (about 60% of the value)**
- One query over the tables you have: `SELECT … FROM sms UNION ALL calls UNION ALL voicemails UNION ALL emails ORDER BY ts`, grouped by normalized number. That is the Everything list, the thread inside a row, and the folder timeline. No new capture code.
- Folders as labels: `item_folder(item_id, folder_id)`. Adding, removing, several folders per item. Folder status active/closed.
- The ⋯ menu: Add to folder (select mode, everything selected, deselect, choose folders), Export this conversation.
- Bottom row of active folders, most recent first. Folder header, timeline, By person.
- Delete: the All Texts tab, Add Call Log form, Add Voicemail form, Add Conversations sheet, File This Message picker. This is the part that makes it simple, and it is deletion, not construction.

**Iteration 2 · the export the broker asked for**
- Export page with three readiness checks, date range, PDF + ZIP, batch export of several people as separate files, destination sheet (device, Drive, Dropbox, email, share).
- Roles per folder (`folder.roles`), notes on any record with speech input, one color per person, group texts as rooms with senders.
- Unknown and private numbers never block an export.

**Iteration 3 · guidance**
- Eleven one-line tips, shown once, dismissed with Got it. The eight-step tour, text templated from the user's own data. Both are standard Android components (`TapTargetView` / Material tap-target prompts) driven by a small table of strings.
- Permissions that fix themselves: deep links to the exact Android screen, re-check on resume.

Each iteration ships on its own and is useful on its own. The acceptance checklist in `HANDOFF.md` §6 is the definition of done for each.

## Why we are confident it is buildable

- Every screen in the mockup runs on the app's real sample data and is sized for a 360 × 780 dp phone. Nothing in it needs a capability the phone does not give you: the sender of a group message, the participants of a thread, the call log, visual voicemail where the carrier exposes it.
- Nothing in v2 touches the hashed bytes. Roles, notes, folder membership, names and hidden people all live beside the record.
- The mockup is plain HTML and its source is in the repo; every behavior in the spec can be clicked and compared.

## How we would like to work

Bring us the pushback. Where the spec is wrong for Android, or where a shortcut gets the same result, tell us and we will change the spec, not argue. What we will not move on is the user's experience: one list, one menu, four taps to file a conversation, an export that never fails quietly, and an app that tells a first-time user what to do.

The mockup, walkthrough and plan are linked from `PLAN.md`. The spec is `HANDOFF.md`.
