"""
core/runner.py
Inference ONNX thật — nhận ảnh, chạy model, trả ảnh.
Import bởi: ai_engine.py
"""

import numpy as np
import onnxruntime as ort
from PIL import Image
from dataclasses import dataclass


@dataclass
class RunResult:
    success    : bool
    image      : Image.Image | None
    message    : str


def _preprocess(img: Image.Image) -> np.ndarray:
    """PIL → numpy float32 [1, C, H, W] chuẩn ONNX."""
    img = img.convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0
    arr = np.transpose(arr, (2, 0, 1))   # HWC → CHW
    arr = np.expand_dims(arr, axis=0)    # CHW → 1CHW
    return arr


def _postprocess(output: np.ndarray) -> Image.Image:
    """numpy [1, C, H, W] → PIL."""
    out = np.squeeze(output, axis=0)     # 1CHW → CHW
    out = np.transpose(out, (1, 2, 0))  # CHW → HWC
    out = np.clip(out * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGB")


def run_scale(model_path: str, image: Image.Image) -> RunResult:
    """
    Chạy ONNX upscale model.
    Tự tile ảnh nếu quá lớn để tránh OOM.
    """
    try:
        sess = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"]
        )
        input_name  = sess.get_inputs()[0].name
        output_name = sess.get_outputs()[0].name

        w, h = image.size

        # Tile nếu ảnh > 256px — tránh OOM trên thiết bị yếu
        if w > 256 or h > 256:
            result = _run_tiled(sess, input_name, output_name, image)
        else:
            inp    = _preprocess(image)
            output = sess.run([output_name], {input_name: inp})[0]
            result = _postprocess(output)

        return RunResult(True, result, "OK")

    except MemoryError:
        return RunResult(False, None, "Hết RAM khi chạy model — thử ảnh nhỏ hơn")
    except Exception as e:
        return RunResult(False, None, f"Inference lỗi: {e}")


def _run_tiled(sess, input_name: str, output_name: str,
               image: Image.Image, tile_size: int = 128) -> Image.Image:
    """
    Chia ảnh thành tile 128x128, inference từng tile, ghép lại.
    Tránh OOM cho ảnh lớn trên thiết bị ít RAM.
    """
    w, h   = image.size
    # Detect scale factor từ output shape
    test   = image.crop((0, 0, min(32, w), min(32, h)))
    inp    = _preprocess(test)
    out    = sess.run([output_name], {input_name: inp})[0]
    scale  = out.shape[-1] // inp.shape[-1]

    out_w, out_h = w * scale, h * scale
    canvas = Image.new("RGB", (out_w, out_h))

    for y in range(0, h, tile_size):
        for x in range(0, w, tile_size):
            x2 = min(x + tile_size, w)
            y2 = min(y + tile_size, h)
            tile = image.crop((x, y, x2, y2))
            inp  = _preprocess(tile)
            out  = sess.run([output_name], {input_name: inp})[0]
            tile_out = _postprocess(out)
            canvas.paste(tile_out, (x * scale, y * scale))

    return canvas


if __name__ == "__main__":
    import os, sys
    model_path = "models/downloaded/realesrgan-x4-general.onnx"

    if not os.path.exists(model_path):
        print("Chưa có model — vào Settings tải trước")
        sys.exit(1)

    # Test với ảnh giả 64x64
    test_img = Image.new("RGB", (64, 64), color=(106, 90, 205))
    print(f"Input  : {test_img.size}")

    result = run_scale(model_path, test_img)
    print(f"Success: {result.success}")
    print(f"Output : {result.image.size if result.image else 'None'}")
    print(f"Message: {result.message}")
