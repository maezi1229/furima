---
name: quotation-reply
description: Automates replying to a customer's material quotation-request FAX (見積り依頼/見積り依頼書) by writing the marked-up unit price directly back onto a copy of the original request PDF — the exact workflow 阪和興業 厚板部 uses today by hand. Computes supplier cost + 10% markup rounded UP to the nearest 100 yen, fills the answer into the correct cell of the customer's own FAX layout, transcribes any handwritten supplier remarks (freight/運賃, delivery time/納期, material notes), and drafts the accompanying Japanese business email. Use this whenever the user shares a PDF that looks like a 見積り依頼 FAX (from customers such as みなみ興業), shares a supplier's reply to one (handwritten-on-the-same-form or email text), mentions 単価 to write onto a FAX, 10%オン/掛け率/切り上げ pricing, or references 厚板部/前島/仕入先回答 in a quoting context — even if they don't explicitly say "use the quotation skill."
---

# Quotation Reply (見積り依頼への回答)

## The business situation

The user works in 厚板部厚板第二課 at 阪和興業 and receives quotation requests as PDF faxes (見積り依頼 / 見積り依頼書) — usually from みなみ興業. He forwards each request to a supplier, who replies either by:
- **handwriting** the price directly onto the *same* FAX form and sending it back as a photo/scan/PDF, or
- **email text** with a price.

He then hand-writes the marked-up price back onto the **original customer FAX** and sends that same sheet back as the answer. The tooling in `quotation_tool/` automates that final "write the answer back onto the original form" step — it does not replace the human judgment of reading the supplier's numbers or approving the final document.

Treat this as a multi-turn conversation, not a single command: gather what's needed, show your work, and always let the user see the rendered result before it's final.

## Step-by-step

### 1. Figure out what you've been handed

The user will typically paste a PDF. Read it (the `Read` tool handles PDFs) and figure out which of these it is:
- A **customer request** (title reads 見積り依頼/見積り依頼書, has a blank 単価 column) → this is the base document you'll write the answer onto.
- A **supplier reply** (same form, now with handwritten numbers/notes in the margins and table) → this is where the pricing and remarks come from.
- Something else (a new customer's FAX with a layout you haven't seen) → see step 2.

If only the request has arrived so far, acknowledge it and ask the user to forward the supplier's reply when it's in. Don't stall the conversation waiting — just say what you're waiting for.

### 2. Pick (or build) the template

Templates live in `quotation_tool/templates/*.json` and encode one customer FAX layout's pixel-derived coordinates (columns, row bands, header redaction box, note areas). Two exist so far:
- `minami_kogyo_v1.json` — 5-column form (材質/寸法/数量/単価/金額)
- `minami_kogyo_v2_atsuita.json` — 6-column 厚板部 form (材質/寸法/数量/重量/単価/備考, no amount column)

Compare the new PDF against these visually — same customer, same column headers, same layout means reuse the existing template as-is (don't recalibrate every time; these are stable per customer/form).

If it's genuinely a new layout, you need to calibrate a new template. **Read `references/template-calibration.md` before doing this** — it walks through the pixel-scanning + OCR technique used for the first two templates, including the threshold-tuning that faint/dashed fax grid lines need. Do this calibration yourself; don't ask the user for pixel coordinates.

### 3. Auto-read the printed request data

Run `read_request.py` against the customer's request PDF and the chosen template:

```bash
python3 quotation_tool/read_request.py --pdf <customer_fax.pdf> --template quotation_tool/templates/<template>.json --out items.json
```

This OCRs only the **printed** parts of the request (material/dimension/qty) — those are typed/stamped text and OCR reliably. It deliberately leaves `unit_cost` as `null`: never try to OCR a supplier's handwritten price, it doesn't work (verified — garbled output every time it's been tried). Skim the detected rows against the source PDF for OCR slip-ups (stray characters, misread digits) before moving on; read_request.py already filters low-confidence rows, but it's not perfect.

### 4. Get the pricing from the user — and ask what else was written

Since handwriting can't be read automatically, ask the user to tell you what the supplier's reply says: the unit cost(s), and — this matters — **anything else handwritten on it**. Suppliers routinely add things beyond the price that the customer needs to see:
- margin notes near the material column (e.g. brand/processing specs like "ポスコ 切りっぱなし")
- direct answers to a question the customer wrote on their original request (e.g. a delivery-date confirmation)
- extra terms jotted into blank table rows (freight/shipping options, lead times, caveats)

Don't wait for the user to think to mention these — ask directly, e.g. "見積もり以外に何か書き込みはありますか？(運賃、納期、備考など)". The one thing to leave off the customer-facing reply by default is a red circular internal stamp (branch name + date + staff initial, e.g. "阪和下松店 '26.8.24 山口") — that's an internal receipt mark, not customer information. Mention you're excluding it and ask if they actually want it included.

If one supplier quote covers a combined batch spanning multiple request rows (e.g. the same material at qty 1 and qty 20, priced together at a volume rate), the same per-unit price applies to every matching row — write it into each row, not just one.

For quotes with more than one material source (e.g. domestic vs POSCO/imported steel), `unit_cost` in items.json can be a dict instead of a plain number: `{"国内": 6400, "ポスコ": 5700}`. `fill_customer_quote.py` stacks both as separate lines in the 単価 cell automatically.

### 5. Compute and write the reply PDF

Run `fill_customer_quote.py` against the **clean, original** customer request PDF (not the supplier's marked-up copy — you want a tidy typed answer on an unmarked form):

```bash
python3 quotation_tool/fill_customer_quote.py \
  --pdf <customer_fax.pdf> --template quotation_tool/templates/<template>.json \
  --items items.json --output <reply.pdf> \
  --note "<material-spec remark, if any>" \
  --reply-note "<closing-area remark, e.g. a delivery answer>" \
  --row-note "<row>:<freight/delivery/caveat text>" \
  --row-note "<row>:<another one>"
```

The markup (10%) and rounding (**up**, to the nearest ¥100) are the defaults built into `compute_unit_price()` — don't override them unless the user explicitly says a different rate this time. That function uses `Decimal` arithmetic on purpose: plain float math has a real bug here (`42000 * 1.1` in Python floats comes out `46200.00000000001`, which naively rounds up a full step too far to ¥46,300 instead of staying at the correct ¥46,200). If you ever need to compute a price outside of calling this script directly — e.g. marking up a freight quote mentioned in the supplier's notes — import and call `compute_unit_price` from `fill_customer_quote.py` rather than reimplementing the rounding by hand.

That reminder about freight matters: if the supplier's reply mentions a shipping/freight cost, it gets the same 10%-then-ceiling-100 treatment before it goes into the reply, unless the user gives you a specific number to use as-is (a manual override, not derived from markup — use it verbatim, don't recompute it).

**Don't pass `--yes` yet.** Let the script show its preview (it prints every computed item, the header rewrite, and all notes) — read it yourself and sanity-check it against what the user told you before going further.

### 6. Show the user, then confirm

Render the output PDF to an image (`pdfplumber`'s `page.to_image()` at ~200dpi is what's been used throughout) and send it to the user — don't just report numbers in text, they need to see the actual filled-in form, since this is a document going to their customer. Point out anything you're unsure about (an OCR'd dimension you couldn't fully verify, a note placement that might be tight on space). Only treat the PDF as final once the user has looked at it and said it's good — if they ask for a change (a different rate, a corrected note, a different freight number), just regenerate; no need to re-run the earlier steps.

### 7. Draft the email

Once the PDF is approved, offer (or just go ahead and provide) a ready-to-copy 件名 + 本文 for the email that will carry the PDF attachment. Keep it in the polite business register these replies have used: greet the recipient by name, reference the request, summarize the same materials/prices/freight/delivery terms that are on the PDF (don't introduce numbers that aren't already in the document), and close with a standard sign-off using the user's name and department. Present it as plain text in two clearly labeled blocks (件名: / 本文:) so it can be copy-pasted straight into an email client.

## Things that will bite you if you skip them

- **Never** try to OCR a handwritten price. Ask the human.
- **Round up**, not down — this was an explicit correction from the user partway through building this, and it's easy to default to the more "expected" floor/truncate behavior. Ceiling to the nearest round_unit is the rule.
- Use `compute_unit_price()`'s Decimal math for any markup calculation, including one-off ones like freight — don't hand-roll `cost * 1.1` in plain Python.
- A combined-batch price applies to every row it covers, not just the first one.
- Ask explicitly what else is handwritten on the reply besides the price — don't wait for the user to volunteer freight/delivery/spec notes.
- Skip the internal processing stamp by default; ask before including it.
- Always render and show the PDF, and treat the user's look-and-confirm as a required step, not a formality — this document goes out to their customer.
