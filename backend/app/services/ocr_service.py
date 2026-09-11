import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import pytesseract
from PIL import Image

from backend.app.core.exceptions import OcrFailedError

_WINDOWS_TESSERACT_DEFAULT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
if shutil.which("tesseract") is None and _WINDOWS_TESSERACT_DEFAULT.exists():
    pytesseract.pytesseract.tesseract_cmd = str(_WINDOWS_TESSERACT_DEFAULT)


@dataclass
class OcrWord:
    text: str
    confidence: float  # 0-1


@dataclass
class OcrResult:
    text: str
    mean_confidence: float
    words: list[OcrWord]


class OCRProvider(ABC):
    @abstractmethod
    def extract(self, image: Image.Image) -> OcrResult: ...


class TesseractOCRProvider(OCRProvider):
    def extract(self, image: Image.Image) -> OcrResult:
        try:
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        except Exception as exc:
            raise OcrFailedError(f"Tesseract OCR failed: {exc}") from exc

        words: list[OcrWord] = []
        confidences: list[float] = []
        lines: dict[tuple[int, int, int], list[str]] = {}
        line_order: list[tuple[int, int, int]] = []

        n = len(data["text"])
        for i in range(n):
            text = data["text"][i]
            conf_val = float(data["conf"][i])
            if not text.strip() or conf_val < 0:
                continue
            words.append(OcrWord(text=text, confidence=round(conf_val / 100.0, 4)))
            confidences.append(conf_val)

            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            if key not in lines:
                lines[key] = []
                line_order.append(key)
            lines[key].append(text)

        text = "\n".join(" ".join(lines[key]) for key in line_order)
        mean_confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
        return OcrResult(text=text, mean_confidence=round(mean_confidence, 4), words=words)


def get_ocr_provider(provider_name: str) -> OCRProvider:
    if provider_name == "tesseract":
        return TesseractOCRProvider()
    raise ValueError(f"Unsupported OCR_PROVIDER: {provider_name}")
