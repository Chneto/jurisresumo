"""Local offline OCR integration wrapping RapidOCR (ONNX Runtime).

Provides image preprocessing, vector stamp cropping, and structured text line extraction.
"""

import io
import re
from typing import List, Optional, Tuple, Union

import pymupdf
from PIL import Image, ImageEnhance, ImageOps

from app.core.models import OCRLine, OCRResult

# Regular expression to catch any residual PJe stamp lines that might slip into margins
PJE_STAMP_REGEX = re.compile(
    r"(Assinado eletronicamente por:|Num\.\s*\d+\s*-\s*Pág\.|https?://pje|Número do documento:|Pág\.\s*Total)",
    re.IGNORECASE,
)


class OCREngine:
    """Wrapper around RapidOCR (ONNX Runtime) with intelligent cropping and preprocessing."""

    _instance: Optional["OCREngine"] = None

    def __init__(self):
        try:
            import rapidocr_onnxruntime as rocr
            self._ocr = rocr.RapidOCR()
        except Exception as e:
            self._ocr = None
            self._init_error = str(e)
        else:
            self._init_error = None

    @classmethod
    def get_instance(cls) -> "OCREngine":
        """Singleton accessor for OCREngine."""
        if cls._instance is None:
            cls._instance = OCREngine()
        return cls._instance

    @property
    def is_available(self) -> bool:
        """True if RapidOCR was initialized successfully."""
        return self._ocr is not None

    def preprocess_image(
        self,
        image: Image.Image,
        enhance_contrast: bool = True,
        autocontrast: bool = True,
    ) -> Image.Image:
        """Preprocesses PIL image to enhance readability for OCR."""
        # Convert to grayscale
        if image.mode != "L":
            image = image.convert("L")

        if autocontrast:
            image = ImageOps.autocontrast(image, cutoff=1)

        if enhance_contrast:
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.5)

        return image

    def ocr_page(
        self,
        page: pymupdf.Page,
        crop_top: float = 50.0,
        crop_bottom: float = 80.0,
        crop_left: float = 0.0,
        crop_right: float = 0.0,
        dpi: int = 150,
        preprocess: bool = True,
    ) -> OCRResult:
        """Performs OCR on a PDF page, cropping out headers and footers to eliminate stamps.

        Args:
            page: PyMuPDF Page object.
            crop_top: Top margin to exclude in points (default 50 pt).
            crop_bottom: Bottom margin to exclude in points (default 80 pt).
            crop_left: Left margin to exclude in points (default 0 pt).
            crop_right: Right margin to exclude in points (default 0 pt).
            dpi: Resolution for rasterizing the page (default 150 dpi).
            preprocess: Whether to apply contrast enhancement.

        Returns:
            OCRResult containing recognized lines and concatenated text.
        """
        page_rect = page.rect
        y0 = max(0.0, crop_top)
        y1 = max(y0 + 10.0, page_rect.height - crop_bottom)
        x0 = max(0.0, crop_left)
        x1 = max(x0 + 10.0, page_rect.width - crop_right)

        clip_rect = pymupdf.Rect(x0, y0, x1, y1)

        pix = page.get_pixmap(clip=clip_rect, dpi=dpi)
        img_bytes = pix.tobytes("png")

        if preprocess:
            pil_img = Image.open(io.BytesIO(img_bytes))
            pil_img = self.preprocess_image(pil_img)
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            img_bytes = buf.getvalue()

        return self.ocr_image_bytes(img_bytes, page_number=page.number + 1)

    def ocr_image_bytes(
        self,
        img_bytes: bytes,
        page_number: Optional[int] = None,
        filter_stamps: bool = True,
    ) -> OCRResult:
        """Runs OCR on image bytes and parses structured lines."""
        if not self.is_available:
            return OCRResult(
                text="",
                lines=[],
                page_number=page_number,
                is_scanned=True,
            )

        try:
            results, elapse = self._ocr(img_bytes)
        except Exception:
            return OCRResult(
                text="",
                lines=[],
                page_number=page_number,
                is_scanned=True,
            )

        if not results:
            return OCRResult(
                text="",
                lines=[],
                page_number=page_number,
                is_scanned=True,
            )

        ocr_lines: List[OCRLine] = []
        text_lines: List[str] = []

        for item in results:
            # RapidOCR returns list of [box, text, score]
            if not item or len(item) < 3:
                continue

            box = item[0]
            text = str(item[1]).strip()
            try:
                score = float(item[2])
            except (ValueError, TypeError):
                score = 0.0

            if not text:
                continue

            # Optional post-filtering of any remaining stamp text
            if filter_stamps and PJE_STAMP_REGEX.search(text):
                continue

            ocr_lines.append(OCRLine(text=text, confidence=score, box=box))
            text_lines.append(text)

        full_text = "\n".join(text_lines)
        return OCRResult(
            text=full_text,
            lines=ocr_lines,
            page_number=page_number,
            is_scanned=True,
        )


def is_scanned_page(
    page: pymupdf.Page,
    crop_top: float = 50.0,
    crop_bottom: float = 80.0,
    min_body_chars: int = 40,
) -> bool:
    """Classifies whether a page is scanned (image-based) or contains native vector text.

    Uses cropped body text density (excluding header and footer stamps).
    """
    page_rect = page.rect
    clip_rect = pymupdf.Rect(
        0,
        max(0.0, crop_top),
        page_rect.width,
        max(crop_top + 10.0, page_rect.height - crop_bottom),
    )
    body_text = page.get_text(clip=clip_rect).strip()

    # If body text has fewer characters than the threshold, check if there are images
    if len(body_text) < min_body_chars:
        has_images = len(page.get_images()) > 0
        if has_images or len(body_text) < 10:
            return True
        has_drawings = len(page.get_drawings()) > 0
        return has_drawings

    return False
