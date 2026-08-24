# Calibrating a new customer FAX template

A template (`quotation_tool/templates/*.json`) records, in PDF points from the page's top-left corner, where each column and table row sits on one specific customer's request form. You need a new one whenever a customer's FAX layout doesn't match an existing template — different column set, different header wording position, different row spacing.

These FAXes are almost always a single embedded raster image per page (no text layer, no vector lines) — a scanned/faxed document, not a digitally generated PDF. Confirm this first:

```python
import pdfplumber
with pdfplumber.open(path) as pdf:
    page = pdf.pages[0]
    print(page.width, page.height, bool(page.extract_text()), len(page.lines), len(page.rects))
```

If `extract_text()` is empty and there are no lines/rects, you're working from pixels only — that's the normal case for these.

## 1. Render at 300dpi

```python
img = page.to_image(resolution=300).original  # a PIL Image
img.save("render.png")
```

Keep `render_resolution: 300` in the template — all pixel coordinates below assume it, and the conversion to PDF points is `pt = px * 72 / 300` (i.e. `px * 0.24`).

## 2. Find the grid lines

Table borders on a faxed form are often faint or dashed, not solid black — a clean-looking fax might need a dark-pixel-fraction threshold around 0.5–0.6 to detect lines, while a poor-quality one may only get you 0.15–0.3. There's no universal threshold; try a reasonable one first, and if you get zero or absurdly few lines back, lower it and check what the actual max fraction in that region is before concluding the approach won't work:

```python
import numpy as np
from PIL import Image

arr = np.array(Image.open("render.png").convert("L"))
band = arr[y0:y1, x0:x1]              # a horizontal strip roughly covering the table
dark = band < 170                      # tune the brightness cutoff too if needed
row_frac = dark.mean(axis=1)
# try thresholds from 0.6 down to 0.15 until you get a clean, evenly-spaced set of lines
line_rows = [y0 + i for i, f in enumerate(row_frac) if f > THRESHOLD]
# merge consecutive hits (within ~5-8px) into single line positions, then diff them —
# real table rows should come out roughly evenly spaced; a big outlier gap usually means
# one faint line was missed and needs to be interpolated back in
```

Do the same scan transposed (`axis=0` over a vertical strip) for column boundaries. Cross-check whatever you find against the printed header labels — run `pytesseract.image_to_data` over the header row and confirm word positions roughly line up with the column boundaries you detected; header OCR on a faint fax is often poor quality on its own, but it's still useful as a sanity check, not the primary source of truth.

## 3. Convert to points and write the JSON

Structure to match the existing templates:

```json
{
  "page_width_pt": ...,
  "page_height_pt": ...,
  "render_resolution": 300,
  "columns_pt": {
    "material": [x0, x1],
    "dimension": [x0, x1],
    "qty": [x0, x1],
    "unit_price": [x0, x1]
    // add "amount", "weight", "remarks" etc. to match this customer's actual columns
  },
  "header_redact_pt": [x0, y0_top, x1, y1_bottom],
  "reply_to_lines": ["<customer company>　御中", "<contact name>　様"],
  "note_area_pt": [x0, y0_top, x1, y1_bottom],
  "reply_note_area_pt": [x0, y0_top, x1, y1_bottom],
  "header_band_pt": [top, bottom],
  "row_bands_pt": [[top, bottom], [top, bottom], ...]
}
```

Column and area keys are named by role (`material`, `dimension`, `qty`, `unit_price`, and whichever of `amount`/`weight`/`remarks` this form has) — `read_request.py` and `fill_customer_quote.py` both look them up by these names, not by position, so the exact key set can differ between templates as long as `material`/`dimension`/`qty`/`unit_price` are present.

`header_redact_pt` is the box that gets whited out and replaced with `reply_to_lines` — find it the same way (OCR word positions for the original recipient's company/name block, padded a bit).

`note_area_pt` (near the title, for material-spec remarks) and `reply_note_area_pt` (near the closing sentence, for things like a delivery-date answer) are optional per-template convenience areas — add them if the form has an obvious blank space in a consistent spot for that kind of remark. `--row-note` doesn't need a dedicated area; it writes into whatever row's `material`+`dimension` column span you point it at.

## 4. Verify before trusting it

Run `read_request.py` against a real sample from this customer and check the detected rows against the source PDF by eye. Then run `fill_customer_quote.py` with a couple of placeholder prices, render the output, and visually confirm the written text lands inside the right cells and doesn't collide with anything. Expect to nudge a coordinate or two after seeing the first real render — that's normal, not a sign the approach is wrong.
