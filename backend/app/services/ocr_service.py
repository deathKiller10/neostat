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
class OcrResult:
    text: str
    mean_confidence: float


class OCRProvider(ABC):
    @abstractmethod
    def extract(self, image: Image.Image) -> OcrResult: ...


class TesseractOCRProvider(OCRProvider):
    def extract(self, image: Image.Image) -> OcrResult:
        try:
            data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        except Exception as exc:
            raise OcrFailedError(f"Tesseract OCR failed: {exc}") from exc

        words = []
        confidences = []
        for text, conf in zip(data["text"], data["conf"], strict=True):
            if text.strip():
                words.append(text)
            conf_val = float(conf)
            if conf_val >= 0:
                confidences.append(conf_val)

        text = " ".join(words)
        mean_confidence = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0
        return OcrResult(text=text, mean_confidence=round(mean_confidence, 4))


def get_ocr_provider(provider_name: str) -> OCRProvider:
    if provider_name == "tesseract":
        return TesseractOCRProvider()
    raise ValueError(f"Unsupported OCR_PROVIDER: {provider_name}")
