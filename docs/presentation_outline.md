# Presentation outline

Slide-by-slide content for the assignment's PPT deliverable. Each bullet is a talking
point, not a script -- expand in your own words during the actual presentation.

## 1. Problem

- Neostat needs to turn scanned/photographed financial documents (bank statements,
  retail invoices) into structured, validated data without hand-built parsers per
  document type.
- Two very different document families in the sample set: HDFC Bank annual report
  pages (vector-drawn PDFs, no text layer) and Malaysian retail receipts (photographed,
  skewed, dot-matrix print).
- The core risk with any LLM-based extraction pipeline is silent hallucination -- a
  wrong number that looks plausible. The system has to prove it isn't doing that.

## 2. Architecture

- Show `docs/architecture.png`.
- One FastAPI service, one deployment: REST API + server-rendered frontend on the same
  origin.
- Eight-stage synchronous pipeline: validate -> extract text -> LLM structured
  extraction -> ground -> score confidence -> validate financials -> persist -> respond.
- Provider interfaces (`OCRProvider`, `LLMProvider`) so Tesseract/Gemini can be swapped
  without touching the pipeline.

## 3. Pipeline walkthrough

- File validation: sniffs real content type from bytes (not the client's declared
  `Content-Type`), enforces size/page limits, rejects corrupted files -- before any
  paid API call.
- Text extraction: detect a usable PDF text layer (`>100` chars) and use it directly;
  otherwise render the page at 300 DPI and OCR it with Tesseract. Most HDFC pages have
  no text layer at all, so render-then-OCR is the common path for that document type;
  a couple of the cash flow statements do have a real text layer and take the faster,
  more accurate path.
- Walk through one real example: show the rendered page image next to the OCR text
  next to the final extracted JSON.

## 4. Extraction approach and prompt design

- One Pydantic schema per document type (`schemas/extraction.py`), with financial
  statements carrying `periods` + `line_items[].values{period: number}` to preserve
  comparative columns instead of flattening them.
- The LLM gets: document type, the page image, OCR text with line numbers, and the
  target JSON schema (via Gemini's structured-output mode).
- Prompt instructs: transcribe every visible line item (not a fixed list), return
  `null` for anything unreadable, preserve label text verbatim, convert bracketed
  negatives to negative numbers, and quote the exact source line for every field.
- A schema validation failure triggers exactly one retry with the error appended to
  the prompt.

## 5. Grounding and confidence

- After extraction, every numeric value is checked against the page's source text
  (comma/bracket/currency-normalized). A value that isn't found is flagged
  `grounded: false` and its confidence drops sharply -- this is the concrete answer to
  "how do you know it didn't just make that up."
- Confidence formula: `source_confidence x grounding_multiplier`, optionally reduced
  further if the field is an operand in a failing financial check. Fully rule-based,
  documented in the README, never LLM-generated.
- Show a real example where OCR noise caused a correct-looking value to be flagged
  ungrounded (a stray space split a number across two OCR tokens) -- an honest
  limitation, not hidden.

## 6. Financial validation

- Every check: `PASS` / `FAIL` / `NOT_APPLICABLE`, with `NOT_APPLICABLE` used whenever
  an operand is missing rather than substituting a zero.
- Line items are matched to formula operands by normalized label + a synonym map, not
  row position -- LLM output order isn't guaranteed to match a fixed schema.
- Tolerance: `|variance| <= max(ABS_TOL, REL_TOL * |reported|)`, configurable via env.
- Checks run once per comparative period for financial statements (two years per HDFC
  page), independently.

## 7. API and demo

- Show `/docs` (Swagger).
- `curl` walkthrough: upload an invoice, `GET` it back by name, list the dashboard
  data.
- Live demo: upload page -> processing -> result page with highlighted missing/failed/
  ungrounded values -> dashboard search/filter.

## 8. Engineering practices

- Structured JSON logging with a request-id on every line, one line per pipeline
  stage.
- A typed `AppError` hierarchy mapped to the mandated error codes; a catch-all handler
  ensures no stack trace or secret ever reaches the client.
- All DB access goes through one repository class; routes never touch a session
  directly.
- 59+ tests, run without network or an API key (LLM and OCR providers are mocked).

## 9. Results on the sample set

- All 10 balance sheets (2017-2026) processed with `validation.overall_status: PASS`
  on every financial check, confidence ranging 0.60-0.94 -- run against the real
  Gemini API, not mocked. One cash flow statement and one invoice also passed for
  real, all checks green.
- The free-tier key's 20-requests/day cap was hit partway through the full 50-document
  batch (see README "Known limitations") -- re-running
  `scripts/run_samples.py --skip-existing` once quota resets fills in the rest without
  reprocessing what already succeeded.
- Call out one interesting case: the balance sheet grounding check occasionally flags
  a correct value as ungrounded because Tesseract split a large number across two OCR
  tokens with a stray space -- a real, honest limitation, not hidden from the demo.

## 10. Limitations and production roadmap

- Grounding is a strict text match -- it doesn't recover values OCR splits across
  tokens, so real values occasionally show as ungrounded.
- No background job queue -- large batches or many concurrent uploads would need one.
- Confidence penalty from a failing financial check is only applied to invoice
  top-level fields today, not to specific financial-statement line items (see README
  "Known limitations").
- For production: async processing with a job queue and webhook/polling status, an
  admin view for reprocessing failed documents, a second OCR/LLM provider as a
  fallback, and per-document-type prompt tuning based on measured accuracy.
