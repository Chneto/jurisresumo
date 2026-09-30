"""Local offline OCR integration wrapping RapidOCR (ONNX Runtime) and Tesseract fallback.

Provides calibrated image preprocessing, dynamic margin stamp detection, bounding-box
filtering, confidence scoring, and structured text line extraction.

Desenvolvido por FChNeto.
"""

__author__ = "FChNeto"
DEVELOPED_BY = "FChNeto"

import io
import re
from typing import List, Optional, Tuple, Union

import pymupdf
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from app.core.jev_decision_engine import (
    BANKING_NOISE_REGEX,
    PJE_MARGIN_STAMPS_REGEX,
    JEVDecisionEngine,
)
from app.core.models import OCRLine, OCRResult

# Regular expression to catch any residual PJe stamp lines that might slip into margins
PJE_STAMP_REGEX = PJE_MARGIN_STAMPS_REGEX


class OCREngine:
    """Wrapper around RapidOCR (ONNX Runtime) with calibrated preprocessing, margins, and confidence filtering."""

    _instance: Optional["OCREngine"] = None

    def __init__(self):
        try:
            import rapidocr_onnxruntime as rocr
            self._ocr = rocr.RapidOCR()
            self._init_error = None
        except Exception as e:
            self._ocr = None
            self._init_error = str(e)

        # Check optional pytesseract availability
        try:
            import pytesseract
            self._has_tesseract = True
        except ImportError:
            self._has_tesseract = False

    @classmethod
    def get_instance(cls) -> "OCREngine":
        """Singleton accessor for OCREngine."""
        if cls._instance is None:
            cls._instance = OCREngine()
        return cls._instance

    @property
    def is_available(self) -> bool:
        """True if RapidOCR or Tesseract is initialized successfully."""
        return self._ocr is not None or self._has_tesseract

    def preprocess_image(
        self,
        image: Image.Image,
        enhance_contrast: bool = True,
        autocontrast: bool = True,
        sharpen: bool = True,
        adaptive_threshold: bool = False,
    ) -> Image.Image:
        """Preprocesses PIL image to optimize legibility and eliminate scan artifacts.

        Args:
            image: PIL Image in RGB or L mode.
            enhance_contrast: Multiplies image contrast for clearer character separation.
            autocontrast: Stretches histogram to remove background shading/yellowing.
            sharpen: Applies subtle sharpening filter to delineate blurry strokes.
            adaptive_threshold: Applies binarization for degraded or stained scans.

        Returns:
            Preprocessed PIL Image.
        """
        # Convert to grayscale
        if image.mode != "L":
            image = image.convert("L")

        if autocontrast:
            image = ImageOps.autocontrast(image, cutoff=1)

        if enhance_contrast:
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.6)

        if sharpen:
            image = image.filter(ImageFilter.SHARPEN)

        if adaptive_threshold:
            # Otsu-like approximation using point transform on mean luminosity
            hist = image.histogram()
            total_pixels = sum(hist)
            if total_pixels > 0:
                luminance = sum(i * count for i, count in enumerate(hist)) / total_pixels
                threshold = int(luminance * 0.90)
                image = image.point(lambda p: 255 if p > threshold else 0)

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
        dynamic_margins: bool = True,
        min_confidence: float = 0.55,
    ) -> OCRResult:
        """Performs OCR on a PDF page with dynamic margin stamp exclusion and image optimization.

        Args:
            page: PyMuPDF Page object.
            crop_top: Base top margin in points.
            crop_bottom: Base bottom margin in points.
            crop_left: Base left margin in points.
            crop_right: Base right margin in points.
            dpi: Resolution for rasterizing the page (default 150 dpi).
            preprocess: Whether to apply contrast and sharpness enhancement.
            dynamic_margins: When True, adapts crop margins proportionally to page height.
            min_confidence: Minimum character confidence threshold (default 0.55).

        Returns:
            OCRResult containing recognized lines and concatenated clean text.
        """
        page_rect = page.rect

        if dynamic_margins:
            # Dynamic proportional margin detection:
            # PJe header stamps typically occupy the top 5.5% of the page
            # PJe footer stamps (Num. ID - Pág.) occupy the bottom 7.5% of the page
            # Marginal lateral stamps occupy ~3.5%
            y0 = max(crop_top, page_rect.height * 0.055)
            y1 = max(y0 + 20.0, page_rect.height - max(crop_bottom, page_rect.height * 0.075))
            x0 = max(crop_left, page_rect.width * 0.035)
            x1 = max(x0 + 20.0, page_rect.width - max(crop_right, page_rect.width * 0.035))
        else:
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

        return self.ocr_image_bytes(
            img_bytes,
            page_number=page.number + 1,
            filter_stamps=True,
            min_confidence=min_confidence,
        )

    def ocr_image_bytes(
        self,
        img_bytes: bytes,
        page_number: Optional[int] = None,
        filter_stamps: bool = True,
        min_confidence: float = 0.55,
    ) -> OCRResult:
        """Runs OCR on image bytes and parses calibrated, structured lines with noise rejection."""
        if not self.is_available:
            return OCRResult(
                text="",
                lines=[],
                page_number=page_number,
                is_scanned=True,
            )

        results = None
        if self._ocr is not None:
            try:
                results, _ = self._ocr(img_bytes)
            except Exception:
                results = None

        # Fallback to Tesseract if RapidOCR yielded no results and Tesseract is available
        if (not results) and self._has_tesseract:
            try:
                import pytesseract
                pil_img = Image.open(io.BytesIO(img_bytes))
                tess_data = pytesseract.image_to_data(
                    pil_img,
                    lang="por",
                    output_type=pytesseract.Output.DICT,
                )
                tess_lines: List[OCRLine] = []
                current_line_text: List[str] = []
                current_conf: List[float] = []

                n_boxes = len(tess_data["text"])
                for i in range(n_boxes):
                    w_text = tess_data["text"][i].strip()
                    conf = float(tess_data["conf"][i])
                    if not w_text or conf < (min_confidence * 100):
                        continue
                    current_line_text.append(w_text)
                    current_conf.append(conf / 100.0)

                if current_line_text:
                    full_line = " ".join(current_line_text)
                    avg_conf = sum(current_conf) / len(current_conf)
                    tess_lines.append(OCRLine(text=full_line, confidence=avg_conf))

                clean_lines = JEVDecisionEngine.get_instance().filter_ocr_lines(
                    tess_lines, min_confidence=min_confidence
                )
                return OCRResult(
                    text="\n".join(l.text for l in clean_lines),
                    lines=clean_lines,
                    page_number=page_number,
                    is_scanned=True,
                )
            except Exception:
                pass

        if not results:
            return OCRResult(
                text="",
                lines=[],
                page_number=page_number,
                is_scanned=True,
            )

        ocr_lines: List[OCRLine] = []

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

            # 1. Confidence threshold filter
            if score < min_confidence:
                continue

            # 2. Minimum content check (at least 2 alphanumeric chars)
            if not text or sum(c.isalnum() for c in text) < 2:
                continue

            # 3. Bounding box size sanity check (discard tiny artifacts < 7px height or width)
            if box and len(box) >= 4:
                try:
                    xs = [pt[0] for pt in box]
                    ys = [pt[1] for pt in box]
                    box_w = max(xs) - min(xs)
                    box_h = max(ys) - min(ys)
                    if box_w < 7.0 or box_h < 7.0:
                        continue
                except Exception:
                    pass

            # 4. Stamp and banking noise filtering
            if filter_stamps and (PJE_MARGIN_STAMPS_REGEX.search(text) or BANKING_NOISE_REGEX.search(text)):
                continue

            ocr_lines.append(OCRLine(text=text, confidence=score, box=box))

        # Apply JEV Decision Engine line-level filtering
        clean_lines = JEVDecisionEngine.get_instance().filter_ocr_lines(
            ocr_lines, min_confidence=min_confidence
        )
        full_text = "\n".join(line.text for line in clean_lines)

        return OCRResult(
            text=full_text,
            lines=clean_lines,
            page_number=page_number,
            is_scanned=True,
        )


def is_scanned_page(
    page: pymupdf.Page,
    crop_top: float = 50.0,
    crop_bottom: float = 80.0,
    min_body_chars: int = 40,
    dynamic_margins: bool = True,
) -> bool:
    """Classifies whether a page is scanned (image-based) or contains native vector text.

    Uses cropped body text density (excluding header and footer stamps).
    """
    page_rect = page.rect
    if dynamic_margins:
        y0 = max(crop_top, page_rect.height * 0.055)
        y1 = max(y0 + 10.0, page_rect.height - max(crop_bottom, page_rect.height * 0.075))
    else:
        y0 = max(0.0, crop_top)
        y1 = max(crop_top + 10.0, page_rect.height - crop_bottom)

    clip_rect = pymupdf.Rect(
        0,
        y0,
        page_rect.width,
        y1,
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
