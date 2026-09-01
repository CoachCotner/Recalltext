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

## Status

All five files are present and in use.

| File | Location | Notes |
|---|---|---|
| `CommLocker_logo_transparent.png` | `brand/` | **In use** on the sealed-record cover header |
| `CommLocker_logo_2000.png` | `brand/` | Higher-resolution fallback |
| `CommLocker_logo_POP.svg` | `brand/` | Last fallback — see the note below |
| `CommChecker_logo_transparent.png` | `web/` | **In use** on the verify page header |
| `CommChecker_icon.png` | `web/` | **In use** as the browser tab icon |

### A note on `CommLocker_logo_POP.svg`

That file is **not vector artwork**. It contains no `<path>` elements — it is a
base64-encoded PNG wrapped in an `<svg>` element, at the same 2000x965 as
`CommLocker_logo_2000.png`. So it offers no crispness advantage on a PDF while
adding a rendering dependency, and it is tried last rather than first.

This does not affect quality. `CommLocker_logo_transparent.png` is 1330px wide
and is placed about 250pt across, which needs roughly 1040px at 300dpi — so
there is resolution to spare in print.

If true vector artwork is produced later (an SVG built from paths, or a PDF/EPS
export), drop it in and point `COMMCHECKER_COVER_LOGO` at it; the SVG path in
the code already handles real vector.
