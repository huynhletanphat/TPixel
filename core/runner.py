"""
core/runner.py
Inference ONNX thật — cache session, tiled inference.
Import bởi: ai_engine.py
"""

import numpy as np
import onnxruntime as ort
from PIL import Image
from dataclasses import dataclass
from typing import Dict


@dataclass
class RunResult:
    success : bool
    image   : Image.Image | None
    message : str


# Cache session — load model một lần, dùng mãi
_sessions: Dict[str, ort.InferenceSession] = {}


def _get_session(model_path: str) -> ort.InferenceSession:
    if model_path not in _sessions:
        _sessions[model_path] = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"]
        )
    return _sessions[model_path]


def _preprocess(img: Image.Image) -> np.ndarray:
    img = img.convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0
    arr = np.transpose(arr, (2, 0, 1))
    arr = np.expand_dims(arr, axis=0)
    return arr


def _postprocess(output: np.ndarray) -> Image.Image:
    out = np.squeeze(output, axis=0)
    out = np.transpose(out, (1, 2, 0))
    out = np.clip(out * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGB")


def _detect_scale(sess, input_name, output_name) -> int:
    dummy = np.zeros((1, 3, 32, 32), dtype=np.float32)
    out   = sess.run([output_name], {input_name: dummy})[0]
    return out.shape[-1] // 32


def run_scale(model_path: str, image: Image.Image) -> RunResult:
    try:
        sess        = _get_session(model_path)
        input_name  = sess.get_inputs()[0].name
        output_name = sess.get_outputs()[0].name
        w, h        = image.size

        if w > 256 or h > 256:
            result = _run_tiled(sess, input_name, output_name, image)
        else:
            inp    = _preprocess(image)
            output = sess.run([output_name], {input_name: inp})[0]
            result = _postprocess(output)

        return RunResult(True, result, "OK")

    except MemoryError:
        return RunResult(False, None, "Hết RAM — thử ảnh nhỏ hơn")
    except Exception as e:
        return RunResult(False, None, f"Inference lỗi: {e}")


def _run_tiled(sess, input_name, output_name,
               image: Image.Image, tile_size: int = 128) -> Image.Image:
    w, h  = image.size
    scale = _detect_scale(sess, input_name, output_name)
    canvas = Image.new("RGB", (w * scale, h * scale))

    for y in range(0, h, tile_size):
        for x in range(0, w, tile_size):
            tile = image.crop((x, y, min(x+tile_size,w), min(y+tile_size,h)))
            inp  = _preprocess(tile)
            out  = sess.run([output_name], {input_name: inp})[0]
            canvas.paste(_postprocess(out), (x * scale, y * scale))

    return canvas


if __name__ == "__main__":
    import os, sys
    model_path = "models/downloaded/realesrgan-x4-general.onnx"
    if not os.path.exists(model_path):
        print("Chưa có model")
        sys.exit(1)

    img = Image.new("RGB", (32, 32), color=(106, 90, 205))
    r   = run_scale(model_path, img)
    print(f"Success: {r.success}")
    print(f"Output : {r.image.size if r.image else None}")
    print(f"Message: {r.message}")
