# Architecture

![Architecture diagram](architecture.png)

One FastAPI application serves both the REST API (`/api/v1/*`) and the server-rendered
frontend (`/`, `/dashboard`, `/documents/{name}`). There is one deployable service and
one URL; the frontend calls the API over the same origin using `fetch()`.

## Pipeline

A synchronous call to `POST /api/v1/documents/process` runs the full pipeline inline
and returns the finished result in the response body -- there is no background job
queue, because a single document takes a few seconds and the assignment's scale
(dozens of sample documents, not a production ingestion system) doesn't need one.

1. **File validation** (`document_validation_service.py`) -- checks the bytes are
   non-empty, sniffs the real content type instead of trusting the client's
   `Content-Type` header, opens the PDF/image to confirm it isn't corrupted, and
   enforces the page-count and size limits. This runs before any OCR or LLM call so a
   bad upload fails fast and cheaply.

2. **Text extraction** (`extraction_service.py`) -- for each page, checks whether
   PyMuPDF's text layer has more than 100 characters. If so, that text is used
   directly (it's exact, no OCR error). Otherwise the page is rendered to a 300 DPI
   image and run through Tesseract. Every page is also rendered to an image
   regardless of which path was used, because the LLM step needs the image for
   layout context even when the OCR text isn't used.

3. **LLM structured extraction** (`extraction_service.py`, `llm_provider.py`,
   `schemas/extraction.py`) -- one Gemini call per page, given the page image, the
   OCR/text-layer text with line numbers, and a Pydantic JSON schema for the
   document type. The response is validated against the schema; a validation failure
   triggers one retry with the error appended to the prompt.

4. **Grounding check** (`confidence.py`, folded into `extraction_merge.py`) -- every
   extracted number is checked against the page's source text. A number that can't be
   found is marked `grounded: false` and its confidence is cut sharply -- this is the
   direct defense against hallucinated values.

5. **Confidence scoring** (`confidence.py`) -- rule-based, not LLM-generated. See the
   README's "Confidence scoring" section for the exact formula.

6. **Financial validation** (`financial_checks.py`, `financial_checks_statements.py`,
   `financial_validation_service.py`) -- matches line items to formula operands by
   normalized label (with a synonym map), runs each check within a tolerance, and
   marks a check `NOT_APPLICABLE` rather than substituting a zero when an operand is
   missing.

7. **Persistence** (`document_repository.py`) -- the full result is stored as JSON in
   a `documents` row, along with a few indexed columns for the dashboard/list query.
   All database access goes through this one repository class.

8. The same JSON is returned to the caller and, for browser uploads, the page
   redirects to the result view which re-fetches it from `GET /api/v1/documents/{name}`.

## Why a vision LLM instead of a fixed-schema parser

The HDFC statement pages are vector-drawn with no text layer and no embedded images --
`page.get_text()` returns nothing, so a text-only pipeline has nothing to parse without
OCR. And a fixed-schema parser (one regex/template per line item) breaks the moment a
line item's wording or row order shifts between years, which happens across the
2017-2026 samples. A vision LLM given the rendered page image plus OCR text handles
layout variation without per-document-type hardcoded parsing rules, at the cost of
needing the grounding check to catch anything it invents.

## Why Postgres (Neon) instead of SQLite in production

SQLite is fine for the test suite (no server to stand up, fast) but Render's
filesystem is ephemeral -- anything written to disk disappears on redeploy or when the
free-tier service spins down after idling. Neon's free-tier Postgres is a managed,
persistent instance reachable from both the local machine and Render, so the same
`DATABASE_URL` works in both places and processed documents survive a redeploy.
