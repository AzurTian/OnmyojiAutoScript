# -*- coding: utf-8 -*-
"""
PaddleOCR (PP-OCRv6 small) ONNX OCR 引擎。

基于 paddleocr 的 PaddleOCR 类, 固定使用 PP-OCRv6_small 模型(onnxruntime 推理)。
无日志记录部分(OcrLogger 已移除)。

接口兼容:
    TextSystem()                                   # 默认 small
    TextSystem.ocr_single_line(img, model='medium') -> (text, score)
    TextSystem.detect_and_ocr(img, drop_score, unclip_ratio, box_thresh, model='medium') -> list[BoxedResult]
    text_recognizer 属性可被 rpc 模块 monkey-patch 以支持竖排识别。
    默认均使用 small, 仅当显式传 model='medium' 时才切换 medium。
"""
from typing import Optional

import cv2
import numpy as np
from paddleocr import PaddleOCR

# 模型规模 -> (det 模型名, rec 模型名)
_MODEL_NAMES = {
    "small": ("PP-OCRv6_small_det", "PP-OCRv6_small_rec"),
    "medium": ("PP-OCRv6_medium_det", "PP-OCRv6_medium_rec"),
}
# 按 (模型规模, use_angle_cls) 缓存的 PaddleOCR 实例, 避免重复加载模型
_ocr_cache: dict = {}


class BoxedResult:
    box: np.ndarray
    text_img: Optional[np.ndarray] = None
    ocr_text: str
    score: float

    def __init__(self, box, text_img, ocr_text, score):
        self.box = box
        self.text_img = text_img
        self.ocr_text = ocr_text
        self.score = score

    def __str__(self):
        return f'BoxedResult[{self.ocr_text}, {self.score}]'

    def __repr__(self):
        return self.__str__()


class TextSystem:
    """
    PaddleOCR with ONNX Runtime inference engine.
    Compatible interface with the original ppocronnx-based TextSystem.

    The `text_recognizer` attribute can be monkey-patched (by rpc._detect_and_ocr_vertical)
    to support vertical text recognition. When set to a custom callable, it receives
    a list of cropped image arrays and returns list of (text, score) tuples.
    """
    def __init__(
            self,
            use_angle_cls=False,
            box_thresh=0.8,
            unclip_ratio=1.6,
            ort_providers=None,
    ):
        # Map legacy parameter names to paddleocr 3.x parameters
        self._box_thresh = box_thresh
        self._unclip_ratio = unclip_ratio
        self._use_angle_cls = use_angle_cls
        self._ocr = self._get_ocr("small")

        # text_recognizer can be monkey-patched for vertical text support.
        # If None, the built-in OCR pipeline is used by detect_and_ocr.
        # When set to a callable(img_crop_list) -> list[(text, score)], it
        # replaces only the recognition step after detection.
        self.text_recognizer = None

    def _get_ocr(self, model=None):
        """按模型规模获取 PaddleOCR 实例(带缓存), 默认 small。"""
        variant = "medium" if model == "medium" else "small"
        key = (variant, self._use_angle_cls)
        if key not in _ocr_cache:
            det_name, rec_name = _MODEL_NAMES[variant]
            _ocr_cache[key] = PaddleOCR(
                text_detection_model_name=det_name,
                text_recognition_model_name=rec_name,
                engine='onnxruntime',
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=self._use_angle_cls,
            )
        return _ocr_cache[key]

    def ocr_single_line(self, img, model=None):
        """Recognize a single line of text from a cropped image. (纯识别)
        跳过检测模块，直接识别，速度更快。适用于已裁剪好的单行图片。

        Args:
            model: 模型规模 small/medium; 为空时用默认(small)。
        """
        ocr = self._get_ocr(model)
        rec_model = ocr.paddlex_pipeline._pipeline.text_rec_model
        results = list(rec_model.predict(img))
        if not results:
            return "", 0.0

        texts = []
        scores = []
        for r in results:
            t = r.get('rec_text', '')
            s = float(r.get('rec_score', 0.0))
            if t:
                texts.append(t)
                scores.append(s)

        if texts:
            full_text = "".join(texts)
            avg_score = sum(scores) / len(scores)
            return full_text, avg_score

        return "", 0.0

    def detect_and_ocr(self, img: np.ndarray, drop_score=0.5, unclip_ratio=None, box_thresh=None, model=None):
        """Detect text regions and recognize text.

        Args:
            model: 模型规模 small/medium; 为空时用默认(small)。
        """
        ocr = self._get_ocr(model)
        kwargs = {}
        if box_thresh is not None:
            kwargs['text_det_box_thresh'] = box_thresh
        elif self._box_thresh is not None:
            kwargs['text_det_box_thresh'] = self._box_thresh
        if unclip_ratio is not None:
            kwargs['text_det_unclip_ratio'] = unclip_ratio
        elif self._unclip_ratio is not None:
            kwargs['text_det_unclip_ratio'] = self._unclip_ratio
        kwargs['text_rec_score_thresh'] = drop_score

        # If text_recognizer is monkey-patched, use custom recognition pipeline
        if self.text_recognizer is not None:
            return self._detect_and_ocr_custom_rec(
                img, drop_score, unclip_ratio, box_thresh, model
            )

        result = list(ocr.predict(
            img,
            use_textline_orientation=self._use_angle_cls,
            **kwargs,
        ))
        if not result:
            return []
        page = result[0]
        return self._build_results(page, drop_score)

    def _detect_and_ocr_custom_rec(self, img, drop_score, unclip_ratio, box_thresh, model=None):
        """Run detection with OCR pipeline, then use custom recognizer."""
        # First run detection to get boxes
        ocr = self._get_ocr(model)
        kwargs = {}
        if box_thresh is not None:
            kwargs['text_det_box_thresh'] = box_thresh
        elif self._box_thresh is not None:
            kwargs['text_det_box_thresh'] = self._box_thresh
        if unclip_ratio is not None:
            kwargs['text_det_unclip_ratio'] = unclip_ratio
        elif self._unclip_ratio is not None:
            kwargs['text_det_unclip_ratio'] = self._unclip_ratio

        result = list(ocr.predict(
            img,
            use_textline_orientation=self._use_angle_cls,
            **kwargs,
        ))
        if not result:
            return []
        page = result[0]

        dt_polys = page.get('dt_polys', []) or []
        if not dt_polys:
            return []

        # Crop each detected region from the original image
        img_crop_list = []
        for poly in dt_polys:
            poly = np.array(poly, dtype=np.int32)
            x_min = max(0, int(poly[:, 0].min()))
            y_min = max(0, int(poly[:, 1].min()))
            x_max = min(img.shape[1], int(poly[:, 0].max()))
            y_max = min(img.shape[0], int(poly[:, 1].max()))
            crop = img[y_min:y_max, x_min:x_max]
            if crop.size > 0:
                img_crop_list.append(crop)

        # Use the monkey-patched recognizer
        rec_results = self.text_recognizer(img_crop_list)

        items = []
        for i, poly in enumerate(dt_polys):
            if i < len(rec_results):
                text, score = rec_results[i]
                score = float(score)
                if score >= drop_score:
                    box = np.array(poly, dtype=np.float32)
                    items.append(BoxedResult(box, None, text, score))
        return items

    @staticmethod
    def _build_results(page: dict, drop_score: float) -> list:
        """Build BoxedResult list from a page dict returned by paddleocr predict."""
        items = []
        rec_texts = page.get('rec_texts', []) or []
        rec_scores = page.get('rec_scores', []) or []
        rec_polys = page.get('rec_polys', []) or []
        dt_polys = page.get('dt_polys', []) or []

        # Use rec_polys if available (aligned with rec_texts), otherwise dt_polys
        polys = rec_polys if rec_polys else dt_polys

        for i, text in enumerate(rec_texts):
            score = float(rec_scores[i]) if i < len(rec_scores) else 0.0
            if score >= drop_score:
                if i < len(polys):
                    box = np.array(polys[i], dtype=np.float32)
                else:
                    box = np.zeros((4, 2), dtype=np.float32)
                items.append(BoxedResult(box, None, text, score))
        return items


def sorted_boxes(dt_boxes):
    """
    Sort text boxes in order from top to bottom, left to right
    args:
        dt_boxes(array):detected text boxes with shape [4, 2]
    return:
        sorted boxes(array) with shape [4, 2]
    """
    num_boxes = dt_boxes.shape[0]
    sorted_boxes = sorted(dt_boxes, key=lambda x: (x[0][1], x[0][0]))
    _boxes = list(sorted_boxes)

    for i in range(num_boxes - 1):
        for j in range(i, -1, -1):
            if abs(_boxes[j + 1][0][1] - _boxes[j][0][1]) < 10 and \
                    (_boxes[j + 1][0][0] < _boxes[j][0][0]):
                tmp = _boxes[j]
                _boxes[j] = _boxes[j + 1]
                _boxes[j + 1] = tmp
            else:
                break
    return _boxes
