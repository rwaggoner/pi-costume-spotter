"""YOLOv8 person detector on ONNX Runtime — the windows profile's detector (ADR-010).

The Hailo detector's stand-in on hardware without a Hailo chip: same model
family (YOLOv8), same Detector contract, so tracking/identification/dashboard
can't tell the difference. Runs on the CPU (``[onnx]`` extra) or on any
DirectX 12 GPU (``[directml]`` extra, ONNX_PROVIDER=directml).

Model: a standard Ultralytics export, ``yolo export model=yolov8n.pt
format=onnx`` (docs/setup-windows.md §3). Input ``(1, 3, S, S)`` RGB float 0..1;
output ``(1, 84, N)`` — per candidate box: cx, cy, w, h in input pixels, then 80
COCO class scores (YOLOv8 has no separate objectness). YOLO11 exports share the
format and work too. The model file is not in git: the weights carry
Ultralytics' AGPL-3.0 terms (ADR-010).

Unlike hailo.py (which stretches the frame), this letterboxes: scale to fit,
pad with grey. That keeps people's proportions, which is what the model was
trained on, and the un-letterbox math in ``decode`` maps boxes back exactly.
"""

from pathlib import Path

import numpy as np
from PIL import Image

from costume_spotter.detection.base import Detector
from costume_spotter.events.events import BoundingBox, Detection

_PERSON_CLASS = 0  # COCO "person" — the only class we act on
_NMS_IOU = 0.45  # overlap above which two person boxes are the same person
_PAD_VALUE = 114  # Ultralytics' letterbox grey

# ONNX_PROVIDER -> ONNX Runtime execution providers, in preference order.
_PROVIDERS = {
    "cpu": ["CPUExecutionProvider"],
    "directml": ["DmlExecutionProvider", "CPUExecutionProvider"],
}


def letterbox(frame: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    """Fit an RGB frame into a size x size square without distortion.

    Returns the model input tensor (1, 3, size, size) float32 0..1, plus the
    scale and (left, top) padding needed to map boxes back to the frame.
    """
    h, w = frame.shape[:2]
    scale = min(size / w, size / h)
    new_w, new_h = round(w * scale), round(h * scale)
    resized = np.asarray(Image.fromarray(frame).resize((new_w, new_h), Image.BILINEAR))
    canvas = np.full((size, size, 3), _PAD_VALUE, dtype=np.uint8)
    left, top = (size - new_w) // 2, (size - new_h) // 2
    canvas[top:top + new_h, left:left + new_w] = resized
    tensor = canvas.transpose(2, 0, 1)[np.newaxis].astype(np.float32) / 255.0
    return np.ascontiguousarray(tensor), scale, left, top


def nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> list[int]:
    """Greedy non-maximum suppression over (N, 4) x1,y1,x2,y2 boxes; returns kept indices."""
    order = np.argsort(-scores)
    areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    keep: list[int] = []
    while order.size:
        best, rest = order[0], order[1:]
        keep.append(int(best))
        ix1 = np.maximum(boxes[best, 0], boxes[rest, 0])
        iy1 = np.maximum(boxes[best, 1], boxes[rest, 1])
        ix2 = np.minimum(boxes[best, 2], boxes[rest, 2])
        iy2 = np.minimum(boxes[best, 3], boxes[rest, 3])
        inter = np.clip(ix2 - ix1, 0, None) * np.clip(iy2 - iy1, 0, None)
        iou = inter / (areas[best] + areas[rest] - inter + 1e-9)
        order = rest[iou <= iou_threshold]
    return keep


def decode(output: np.ndarray, *, scale: float, left: int, top: int,
           frame_w: int, frame_h: int, threshold: float) -> list[Detection]:
    """YOLOv8 raw output (1, 4 + classes, N) -> person Detections in frame pixels.

    Pure numpy so it is tested without a model file (tests/test_onnx_yolo.py).
    """
    preds = output[0]  # (4 + classes, N)
    scores = preds[4 + _PERSON_CLASS]
    mask = scores >= threshold  # 01-F5, at the source
    if not mask.any():
        return []
    cx, cy, w, h = preds[:4, mask]
    scores = scores[mask]
    # Input-pixel centre boxes -> frame-pixel corners (undo padding, then scale).
    x1 = (cx - w / 2 - left) / scale
    y1 = (cy - h / 2 - top) / scale
    x2 = (cx + w / 2 - left) / scale
    y2 = (cy + h / 2 - top) / scale
    boxes = np.stack([x1, y1, x2, y2], axis=1)
    boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, frame_w)  # contract: inside the frame
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, frame_h)

    detections = []
    for i in nms(boxes, scores, _NMS_IOU):
        bx1, by1, bx2, by2 = boxes[i]
        x, y = int(bx1), int(by1)
        width, height = int(bx2) - x, int(by2) - y
        if width <= 0 or height <= 0:
            continue
        detections.append(Detection(box=BoundingBox(x, y, width, height),
                                    confidence=round(float(scores[i]), 2)))
    return detections


class OnnxYoloDetector(Detector):
    """People via a YOLOv8 ONNX model on ONNX Runtime (CPU or DirectML)."""

    name = "onnx-yolov8"

    def __init__(self, model_path: Path | str, confidence_threshold: float = 0.5,
                 provider: str = "cpu") -> None:
        try:
            import onnxruntime as ort
        except ImportError as exc:  # fail fast with the fix (01-F6)
            raise RuntimeError(
                "DETECTOR=onnx needs ONNX Runtime: pip install -e \".[onnx]\" "
                "(or \".[directml]\" for a GPU)"
            ) from exc
        model_path = Path(model_path)
        if not model_path.is_file():
            raise RuntimeError(
                f"ONNX model not found: {model_path} — export it once with "
                "edge/deploy/windows/export-model.ps1 (docs/setup-windows.md §3)"
            )
        if provider not in _PROVIDERS:
            raise ValueError(f"unknown ONNX_PROVIDER {provider!r} — use cpu or directml")
        wanted = _PROVIDERS[provider]
        if wanted[0] not in ort.get_available_providers():
            raise RuntimeError(
                f"ONNX_PROVIDER={provider} but {wanted[0]} isn't available — install "
                "onnxruntime-directml and uninstall plain onnxruntime (they conflict)"
            )
        self._threshold = confidence_threshold
        self._session = ort.InferenceSession(str(model_path), providers=wanted)
        model_input = self._session.get_inputs()[0]
        self._input_name = model_input.name
        size = model_input.shape[2]
        self._size = size if isinstance(size, int) else 640  # dynamic-shape exports
        self.name = f"onnx-{model_path.stem}"  # e.g. onnx-yolov8n, recorded on sightings

    def detect(self, frame: np.ndarray) -> list[Detection]:
        frame_h, frame_w = frame.shape[:2]
        tensor, scale, left, top = letterbox(frame, self._size)
        (output,) = self._session.run(None, {self._input_name: tensor})
        return decode(output, scale=scale, left=left, top=top,
                      frame_w=frame_w, frame_h=frame_h, threshold=self._threshold)
