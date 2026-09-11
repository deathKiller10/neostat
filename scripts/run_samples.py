"""Batch-processes sample_documents/ through the real pipeline (file validation, OCR,
Gemini extraction, financial validation, persistence) and writes one JSON result per
file to sample_outputs/. Paces itself between documents because the Gemini free tier
has a low per-minute request cap -- a full run without a delay can exhaust the quota
partway through a 48-document batch.

Usage:
    python scripts/run_samples.py [--limit N] [--delay SECONDS] [--skip-existing]
"""

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import get_settings  # noqa: E402
from backend.app.core.database import SessionLocal, init_db  # noqa: E402
from backend.app.core.exceptions import AppError  # noqa: E402
from backend.app.services.document_service import DocumentService  # noqa: E402

SAMPLE_DIRS = {
    "Balance Sheet": "balance_sheet",
    "Cash Flows": "cash_flow_statement",
    "Profit & Loss": "profit_and_loss",
    "Invoices": "invoice",
}


def discover_samples(sample_root: Path) -> list[tuple[Path, str]]:
    files = []
    for dirname, document_type in SAMPLE_DIRS.items():
        directory = sample_root / dirname
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.is_file():
                files.append((path, document_type))
    return files


def output_path(output_root: Path, document_type: str, source_path: Path) -> Path:
    return output_root / document_type / f"{source_path.stem}.json"


def process_one(service: DocumentService, path: Path, document_type: str) -> dict:
    content = path.read_bytes()
    try:
        return service.process_upload(content, path.name, document_type)
    except AppError as exc:
        return {"error": {"code": exc.code, "message": exc.message}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Process at most N documents.")
    parser.add_argument("--delay", type=float, default=None, help="Seconds to sleep between documents.")
    parser.add_argument(
        "--skip-existing", action="store_true", help="Skip files that already have a JSON output."
    )
    args = parser.parse_args()

    settings = get_settings()
    delay_seconds = args.delay if args.delay is not None else settings.sample_run_delay_seconds

    sample_root = PROJECT_ROOT / "sample_documents"
    output_root = PROJECT_ROOT / "sample_outputs"
    samples = discover_samples(sample_root)
    if args.limit:
        samples = samples[: args.limit]

    init_db()
    db = SessionLocal()
    service = DocumentService(db, settings)

    processed, skipped, failed = 0, 0, 0
    for index, (path, document_type) in enumerate(samples):
        out_path = output_path(output_root, document_type, path)
        if args.skip_existing and out_path.exists():
            skipped += 1
            continue

        print(f"[{index + 1}/{len(samples)}] {document_type}: {path.name}")
        result = process_one(service, path, document_type)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

        if "error" in result:
            failed += 1
            print(f"  -> error: {result['error']['code']}")
        else:
            processed += 1
            print(f"  -> {result['processing_status']} (confidence {result['overall_confidence']})")

        if index < len(samples) - 1:
            time.sleep(delay_seconds)

    db.close()
    print(f"\nDone. processed={processed} failed={failed} skipped={skipped}")


if __name__ == "__main__":
    main()
