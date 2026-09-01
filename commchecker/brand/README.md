# Brand assets

Two products, two logos. Keeping them straight matters:

> **CommLocker seals it** — its logo goes on the sealed record (the cover page
> a broker opens).
> **CommChecker checks it** — its logo goes on the verify tool (the PASS/FAIL
> page).

**Use these files exactly as supplied. Do not recolor, flatten, trace, or
regenerate them.** The bright "pop" CommLocker logo stays bright.

## Files this project looks for

### CommLocker — the sealed record cover page

Put these in this folder (`commchecker/brand/`):

| File | Used for |
|---|---|
| `CommLocker_logo_transparent.png` | **The navy header of the cover page.** Tried first — it is the one made to sit on a dark background. |
| `CommLocker_logo_POP.svg` | Vector, stays crisp at any size. Used if the transparent PNG is absent. |
| `CommLocker_logo_2000.png` | Raster backup if neither of the above is present. |

Override the choice with `COMMCHECKER_COVER_LOGO=/path/to/file`.

If none is present the cover page falls back to a plain type-set wordmark, so
sealing never breaks for a missing file.

### CommChecker — the verify web tool

Put these in `commchecker/web/`:

| File | Used for |
|---|---|
| `CommChecker_logo_transparent.png` | The navy header of the verify page |
| `CommChecker_icon.png` | The browser tab / app icon |

## Brand colours

| | Hex |
|---|---|
| Navy | `#071B42` |
| Burnt orange | `#C56230` |
| Soft white | `#EDEDED` |

---

## Status of the files currently in this repository

| File | Status |
|---|---|
| `web/CommChecker_logo_transparent.png` | **OUTDATED** — carries the old tagline *"CHECKED. VERIFIED. UNCHANGED."* The current mark reads *"CHECKED. CONFIRMED. FLAGGED."* Replace this file. |
| `web/CommChecker_icon.png` | From the original prototype; replace with the current icon. |
| `brand/CommLocker_logo_*` | **NOT PRESENT.** Until one is added, the sealed-record cover page sets its header in type instead of artwork. |

Replacing them is a straight file overwrite — same filenames, no code change.
