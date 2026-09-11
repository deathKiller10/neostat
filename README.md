# Neostat Document Intelligence

An internship case-study submission: a document intelligence platform that takes an
uploaded invoice or HDFC Bank financial statement, extracts structured data with a
vision LLM, checks that every number it produced actually appears in the source
document, runs the appropriate financial arithmetic checks, and serves both a REST API
and a browser dashboard from one deployed service.

## Overview

The pipeline is: upload -> file validation -> text extraction (native PDF text layer,
or render-to-image + OCR when there isn't one) -> LLM structured extraction against a
Pydantic schema -> a grounding check that every extracted number appears in the source
text -> financial validation -> persistence -> JSON response. The same FastAPI app also
serves a small server-rendered frontend (upload form, dashboard, per-document result
page) so there is one URL to open, not a separate API host and frontend host.

## Architecture

![Architecture diagram](docs/architecture.png)

See [`docs/architecture.md`](docs/architecture.md) for the stage-by-stage writeup. The
diagram is generated from [`docs/generate_architecture_diagram.py`](docs/generate_architecture_diagram.py)
(matplotlib) so it's reproducible from source rather than a static image someone has to
hand-edit.

## Tech stack, and why

- **FastAPI + Uvicorn, Pydantic v2** -- one process serves the API and the HTML pages;
  Pydantic schemas double as the extraction contract the LLM's output is validated
  against, not just request/response typing.
- **Render-then-OCR for the bank statements, not a text-only pipeline.** Most of the
  HDFC Bank annual report pages are vector-drawn PDFs with no text layer and no
  embedded images -- `page.get_text()` returns an empty string. The only way to read
  them is to rasterize the page (PyMuPDF `get_pixmap(dpi=300)`) and OCR the image. A
  couple of the cash flow statement pages do carry a real text layer, so each page is
  checked individually (`len(page.get_text().strip()) > 100`) and the text layer is
  used directly when it's there, since it's more accurate than OCR.
- **A vision LLM (Gemini 2.5 Flash) rather than a fixed-schema/regex parser.** Line
  item wording and row order shift across the 2017-2026 statement samples, and the
  invoice layouts vary between a Malaysian SROIE-style receipt format and a different
  general invoice format. A model given the page image plus OCR text handles layout
  variation without a hand-built template per document type per year. The tradeoff is
  that an LLM can invent plausible-looking numbers, which is why the grounding check
  exists as a separate, deterministic step downstream of it.
- **Postgres (Neon) instead of SQLite in production.** Render's filesystem is
  ephemeral -- anything written to disk is gone after a redeploy or when the free-tier
  service spins back up from idle. Neon's free-tier Postgres is a managed instance
  reachable from both the local machine and Render with the same connection string, so
  processed documents persist across deploys. SQLite is still used for the test suite,
  since spinning up a real database for unit tests is unnecessary overhead; the model
  layer is kept dialect-portable (`JSON` with a `JSONB` variant bound only for
  Postgres) so both work without special-casing.
- **Tesseract via `pytesseract`, behind an `OCRProvider` interface.** Tesseract gives
  word-level confidence scores, which the confidence formula uses directly (see below).
  It's swappable via `OCR_PROVIDER` without touching call sites, in case a hosted OCR
  API is preferred later.
- **Gemini behind an `LLMProvider` interface**, selected via `LLM_PROVIDER`, for the
  same reason -- provider lock-in shouldn't require rewriting the extraction service.
- **structlog-style JSON logging via stdlib `logging`** with a request-id middleware,
  so every log line from a single request can be grep'd together in production.

## Local setup

Requirements: Python 3.11+, Tesseract OCR installed and on `PATH` (or set
`pytesseract.pytesseract.tesseract_cmd`), a Neon Postgres connection string (or leave
`DATABASE_URL` as the SQLite default for local-only testing).

```bash
python -m venv .venv
.venv/Scripts/activate        # or source .venv/bin/activate on macOS/Linux
pip install -r backend/requirements.txt
cp .env.example .env          # fill in GOOGLE_API_KEY and DATABASE_URL
uvicorn backend.app.main:app --reload
```

Then open `http://127.0.0.1:8000/` for the upload page, `/dashboard` for the document
list, and `/docs` for the Swagger UI.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql://user:password@host/dbname?sslmode=require` (example) | Postgres connection string from Neon. A bare `postgres://`/`postgresql://` prefix is rewritten to `postgresql+psycopg://` automatically, so Neon's string can be pasted verbatim. |
| `GOOGLE_API_KEY` | *(required for real extraction)* | Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey). |
| `OCR_PROVIDER` | `tesseract` | Selects the `OCRProvider` implementation. |
| `LLM_PROVIDER` | `gemini` | Selects the `LLMProvider` implementation. |
| `LLM_MODEL` | `gemini-2.5-flash` | Gemini model name. |
| `MAX_UPLOAD_MB` | `10` | Rejects uploads larger than this with `FILE_TOO_LARGE`. |
| `MAX_PAGE_COUNT` | `3` | Rejects PDFs with more pages than this with `PAGE_LIMIT_EXCEEDED`. |
| `VALIDATION_ABS_TOL` | `1.00` | Absolute tolerance for financial checks. |
| `VALIDATION_REL_TOL` | `0.005` | Relative tolerance (0.5%) for financial checks. |
| `SAMPLE_RUN_DELAY_SECONDS` | `6` | Delay between documents in `scripts/run_samples.py`, to stay under the Gemini free-tier per-minute request cap. |
| `CORS_ALLOW_ORIGINS` | `*` | Comma-separated allowed origins. |
| `APP_ENV` | `development` | Reported by `/api/v1/health`. |
| `LOG_LEVEL` | `INFO` | Python logging level. |

## Live URLs

- Frontend: `TODO -- fill in after Render deploy`
- API base: `TODO -- same host, path prefix /api/v1`
- Swagger / OpenAPI docs: `TODO -- same host, path /docs`
- GitHub repository: `TODO -- paste the public repo URL`

The frontend and the API are the same deployed service -- there is no separate
frontend host. The four links above will resolve to the same Render URL with
different paths (except GitHub).

## API examples

### `POST /api/v1/documents/process`

```bash
curl -X POST https://<host>/api/v1/documents/process \
  -F "file=@sample_documents/Invoices/X51005361895.jpg" \
  -F "document_type=invoice"
```

```json
{
  "document_name": "X51005361895.jpg",
  "document_type": "invoice",
  "processing_status": "PASS",
  "overall_confidence": 0.76,
  "file_validation": { "file_type": "image/jpeg", "is_supported": true, "is_readable": true, "page_count": 1, "status": "PASS" },
  "extracted_data": {
    "total_amount": { "value": 9.0, "confidence": 0.83, "page_number": 1, "source_text": "Total Includes GST 6% 9.00", "grounded": true },
    "line_items": [ { "description": "SUMMER CUP 48X230ML", "quantity": 1, "unit_price": 8.49, "amount": 8.49 } ]
  },
  "validation": {
    "checks": [ { "name": "invoice_tax_inclusive_total_check", "formula": "gst_taxable_amount + gst_amount", "calculated_value": 9.0, "reported_value": 9.0, "variance": 0.0, "status": "PASS" } ],
    "overall_status": "PASS",
    "issues": []
  },
  "processing_metadata": { "ocr_used": true, "ocr_engine": "tesseract", "llm_model": "gemini-2.5-flash", "text_source": "rendered_ocr", "processed_at": "2026-09-11T07:48:30Z", "processing_time_ms": 858 }
}
```

(Trimmed -- the full response includes every field in `extracted_data`, not just the
two shown above.)

### `GET /api/v1/documents/{document_name}`

```bash
curl https://<host>/api/v1/documents/X51005361895.jpg
```

Returns the same shape as above, for the most recently processed upload with that
name (case-insensitive, falls back to matching without the file extension).

### `GET /api/v1/documents`

```bash
curl "https://<host>/api/v1/documents?limit=20&offset=0&document_type=invoice"
```

```json
{
  "items": [
    { "id": 3, "document_name": "X51005361895.jpg", "document_type": "invoice", "processing_status": "PASS", "overall_confidence": 0.76, "processed_at": "2026-09-11T07:48:30Z", "processing_time_ms": 858, "file_size_bytes": 223437, "page_count": 1, "error_code": null }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

### `GET /api/v1/health`

```bash
curl https://<host>/api/v1/health
```

```json
{ "status": "ok", "app_env": "production" }
```

## OCR and LLM services

- **Tesseract OCR** (local binary via `pytesseract`) -- no request limit since it runs
  locally, but accuracy on skewed/low-contrast photographed receipts is noticeably
  worse than a hosted vision model, which is part of why the LLM is given both the OCR
  text and the raw page image rather than OCR text alone.
- **Gemini 2.5 Flash** (Google AI Studio free tier) -- low per-minute request quota and
  a daily cap. `llm_provider.py` retries on HTTP 429/503 with exponential backoff and
  jitter (respecting `Retry-After` when present), capped at 4 attempts, before raising
  `LLM_RATE_LIMITED` (503) rather than hanging indefinitely. `scripts/run_samples.py`
  sleeps `SAMPLE_RUN_DELAY_SECONDS` (default 6s) between documents so a full batch run
  over the sample set doesn't exhaust the daily quota partway through.

## Confidence scoring

Rule-based and fully explainable -- never LLM-generated. For each extracted field:

```
field_confidence = source_confidence * grounding_multiplier * validation_penalty
```

- `source_confidence`: `0.99` when the value came from a native PDF text layer
  (effectively no OCR error to account for). Otherwise, the Tesseract confidence of
  the OCR word whose parsed numeric value matches the extracted value, or the page's
  overall mean OCR confidence when no single token matches (this happens when a value
  is split across OCR tokens, e.g. a currency symbol in its own token).
- `grounding_multiplier`: `1.0` if the value is found in the page's source text
  (comma/bracket/currency-normalized), `0.35` if it can't be found at all -- a strong
  signal the model may have invented it.
- `validation_penalty`: `0.85` if the field is an operand in a financial check that
  came back `FAIL`, otherwise `1.0`. This is currently applied to invoice fields only
  (see "Known limitations").

`overall_confidence` is the mean of every present field's confidence, with the
document type's mandated key fields (`invoice_number`/`total_amount` for invoices;
`statement_title`/`entity_name`/`period_end` for financial statements) weighted 2x.

## Financial validation rules

Tolerance for every check: pass when `|variance| <= max(ABS_TOL, REL_TOL * |reported|)`,
with `ABS_TOL = 1.00` and `REL_TOL = 0.005` (0.5%), both configurable via env. A check
whose operands can't all be found is `NOT_APPLICABLE` -- a missing figure is never
treated as zero, with two deliberate exceptions noted below. Financial statement
checks run once per comparative period found on the page (HDFC pages show two years
side by side).

**Invoice**
- `quantity * unit_price ≈ amount` per line item.
- `sum(line_item.amount) ≈ subtotal` (or `≈ total` when no subtotal is present).
- `subtotal + tax_amount - discount ≈ total` (tax-exclusive). *A missing discount
  defaults to 0 here rather than making the check `NOT_APPLICABLE`, since a receipt
  with no discount line means no discount was given, not an unknown value.*
- `gst_taxable_amount + gst_amount ≈ total` (tax-inclusive, for GST receipts where the
  displayed total already includes tax).
- `cash_paid - total_amount ≈ change_given`, when both are present.

**Balance sheet** (per period)
- `total_capital_and_liabilities ≈ total_assets`.
- `sum(liability section line items, excluding the Total row) ≈ total_capital_and_liabilities`.
- `sum(asset section line items, excluding the Total row) ≈ total_assets`.

**Profit & loss** (per period)
- `interest_earned + other_income ≈ total_income`.
- `interest_expended + operating_expenses + provisions_and_contingencies ≈ total_expenditure`.
- `total_income - total_expenditure ≈ consolidated_net_profit_before_minority_interest`.
- `net_profit_before_minority_interest - minority_interest ≈ net_profit_attributable_to_group`.
- `current_profit + brought_forward_profit ≈ total_available_for_appropriation`, where
  an appropriations section is present.

**Cash flow statement** (per period)
- `operating_activities + investing_activities + financing_activities + fx_adjustment ≈ net_increase_in_cash`.
  *A missing FX adjustment line defaults to 0, same reasoning as the invoice discount.*
- `opening_cash + net_increase_in_cash + cash_acquired_on_amalgamation ≈ closing_cash`.
  *Cash acquired on amalgamation defaults to 0 when absent, for the same reason.*

Line items are matched to formula operands by normalizing the label (lowercase, strip
punctuation) and comparing against a synonym list per operand, not by row position --
LLM output order isn't guaranteed to match any fixed schema. An exact normalized-label
match always wins over a substring match, so a row like "Minority interest" isn't
shadowed by a longer row that happens to contain the same phrase (e.g. "...profit
before minority interest").

### `processing_status` vs `validation.overall_status`

These answer different questions and are kept separate on purpose.
`processing_status` is `PASS` whenever the pipeline produced a well-formed result with
at least the mandated minimum fields for that document type (e.g. a total amount or
invoice number for an invoice); it's `FAILED` only when extraction came back
essentially empty. `validation.overall_status` is `FAIL` whenever any financial check
failed. A document can process successfully (`processing_status: "PASS"`) while its
numbers don't add up (`validation.overall_status: "FAIL"`) -- that combination is the
expected, useful signal that something in the source document (or the extraction) is
inconsistent, not a pipeline error.

## Persistence

One `documents` table (`backend/app/models/document.py`): id, name, type, status,
overall confidence, the full result as JSON, timestamps, file size, page count, and an
error code column. All access goes through `DocumentRepository` -- routes and services
never hold a raw SQLAlchemy session. Re-processing a file with the same name inserts a
new row rather than overwriting the old one, so `GET /api/v1/documents/{name}` (which
returns the newest row by `processed_at`) reflects the latest run while history is kept
for free. `pool_pre_ping=True` is set because Neon suspends an idle free-tier database,
and the first query after a suspend would otherwise hit a stale pooled connection.

## Tests

```bash
pytest
```

59 tests, none requiring network access or a real API key -- the LLM and OCR providers
are mocked in `test_api.py` and `test_extraction.py`. Coverage:

- `test_numbers.py` -- the number parser: bracketed negatives, thousands separators,
  `₹`/`` ` ``/`RM` currency glyphs, dash-as-nil, junk input.
- `test_validation.py` -- every file-validation error code, and every financial check
  including `NOT_APPLICABLE` on a missing operand and the tolerance boundary.
- `test_extraction.py` -- schema validation and the grounding check (a deliberately
  hallucinated value is caught and its confidence drops).
- `test_api.py` -- health check, the upload happy path, unsupported-type rejection,
  page-limit rejection, `GET` by name returning the latest run, `GET` list, and the
  404 error shape.

## Known limitations

- **Grounding is a strict text match.** OCR occasionally splits a number across two
  tokens (a stray rendering space in the middle of a large figure), which makes a
  correct value show up as ungrounded. Merging adjacent number tokens would fix this
  but risks merging two genuinely separate numbers that happen to sit next to each
  other, so it was left as a documented tradeoff rather than "fixed" with a heuristic
  that could introduce a worse failure mode.
- **The validation-failure confidence penalty only applies to invoice fields**, where
  the check's operand names match `extracted_data`'s top-level keys directly. For
  financial statements, operand names resolve to specific line items via label
  matching, and propagating the penalty back to that exact line item/period was cut
  for scope -- grounding-based confidence still reflects accuracy there, just not the
  extra validation-failure signal.
- **No background job queue.** Processing is synchronous inside the request; a large
  batch or many concurrent uploads would need one.
- **No temp file is written for uploads.** PyMuPDF and Pillow both accept in-memory
  byte streams directly, so the upload is processed entirely in memory and never
  touches disk -- which also means the client's filename is never used to construct a
  filesystem path. This is a deliberate deviation from "save to a temp file with a
  generated name and delete in a `finally`": since disk I/O isn't needed at all, not
  writing the file sidesteps the same risk (path injection, leftover temp files) more
  directly than the delete-in-`finally` pattern does.
- Balance sheet / P&L / cash flow section matching (which rows count as "liabilities"
  vs "assets") relies on the LLM having populated a `section` label per line item
  consistently; if it doesn't, the component-sum checks return `NOT_APPLICABLE` rather
  than a wrong number.

## What I'd change for production

- A job queue (even a simple one) so uploads return immediately with a status to poll,
  instead of blocking the request for the full pipeline.
- A second OCR and/or LLM provider as an automatic fallback when the primary is rate
  limited or down, rather than surfacing `LLM_RATE_LIMITED` to the caller.
- Extend the validation-failure confidence penalty to financial statement line items.
- Per-document-type prompt tuning based on measured accuracy against a larger labeled
  sample, rather than the fixed prompt used here.
- Authentication/authorization on the API -- there is currently none, which is fine for
  a graded demo but not for anything handling real financial documents.

## AI-assistant usage declaration

Claude Code was used throughout this project's development: scaffolding the FastAPI
application structure, writing the extraction/validation/persistence services, writing
the test suite, generating the architecture diagram script, and drafting this README.
All generated code was reviewed, run, and tested against the actual sample documents
(including manually checking extracted values against the rendered page images) before
being committed; the design decisions and tradeoffs documented above reflect my own
judgment on this assignment, not unreviewed model output.

## Assumptions

- `document_type` is supplied by the caller (frontend dropdown or API parameter) and
  is never auto-classified from the file content, per the assignment spec.
- The four financial-statement document types share one extraction schema
  (`FinancialStatementExtraction`) since their fields (title, entity, periods, line
  items) are structurally identical; only the financial validation rules differ by
  type.
- A missing discount / FX-adjustment / cash-acquired-on-amalgamation line item is
  treated as zero for its formula (see "Financial validation rules"), on the reasoning
  that these lines are typically absent rather than present-but-unreadable.
- `MAX_UPLOAD_MB` defaults to 10 and `MAX_PAGE_COUNT` to 3, per the spec's stated
  defaults; both are configurable via env for a grader who wants to test the boundary.
