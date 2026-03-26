"""
core/processors.py
Xử lý ảnh: load, validate, upscale Nearest Neighbor
Độc lập hoàn toàn — không import file nào trong project
Import bởi: ai_engine.py
"""

import io
from PIL import Image, ImageFilter
from dataclasses import dataclass


@dataclass
class ProcessResult:
    success    : bool
    image      : Image.Image | None
    message    : str
    input_size : tuple
    output_size: tuple


def validate(image: Image.Image, max_px: int = 4096) -> tuple[bool, str]:
    w, h = image.size
    if w > max_px or h > max_px:
        return False, f"Ảnh quá lớn: {w}x{h}, tối đa {max_px}px"
    return True, "OK"


def load_image(data: bytes) -> tuple[bool, Image.Image | None, str]:
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        return True, img, "OK"
    except Exception as e:
        return False, None, f"Không đọc được ảnh: {e}"


def upscale_nearest(image: Image.Image, scale: int) -> ProcessResult:
    """
    Nearest Neighbor — giữ pixel vuông 100%.
    Đúng cho pixel art, sprite, icon.
    """
    ok, msg = validate(image)
    if not ok:
        return ProcessResult(False, None, msg, image.size, (0,0))

    w, h   = image.size
    result = image.resize((w * scale, h * scale), Image.NEAREST)
    return ProcessResult(True, result, "OK", image.size, result.size)


def upscale_sharp(image: Image.Image, scale: int) -> ProcessResult:
    """
    Nearest + Sharpen — giữ pixel cứng nhưng cạnh sắc hơn một chút.
    """
    ok, msg = validate(image)
    if not ok:
        return ProcessResult(False, None, msg, image.size, (0,0))

    w, h   = image.size
    result = image.resize((w * scale, h * scale), Image.NEAREST)
    result = result.filter(ImageFilter.SHARPEN)
    return ProcessResult(True, result, "OK", image.size, result.size)


def to_bytes(image: Image.Image, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


if __name__ == "__main__":
    img = Image.new("RGB", (32, 32), color=(106, 90, 205))
    r   = upscale_nearest(img, 4)
    print(f"Nearest : {r.input_size} → {r.output_size} — {r.message}")
    r2  = upscale_sharp(img, 4)
    print(f"Sharp   : {r2.input_size} → {r2.output_size} — {r2.message}")
