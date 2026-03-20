"""
core/processors.py
Xử lý ảnh: upscale xBRz, resize, validate input
Độc lập hoàn toàn — không import file nào trong project
Import bởi: ai_engine.py, server.py
"""

import io
from PIL import Image
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
        return False, f"Ảnh quá lớn: {w}x{h}, tối đa {max_px}px mỗi chiều"
    if image.mode not in ("RGB", "RGBA", "P"):
        return False, f"Định dạng màu không hỗ trợ: {image.mode}"
    return True, "OK"


def load_image(data: bytes) -> tuple[bool, Image.Image | None, str]:
    try:
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        return True, img, "OK"
    except Exception as e:
        return False, None, f"Không đọc được ảnh: {e}"


def _xbrz_scale(img: Image.Image, scale: int) -> Image.Image:
    """
    xBRz thuần Python qua Pillow LANCZOS — giữ cạnh pixel sắc hơn NEAREST
    nhưng nhẹ hơn model AI. Đủ dùng cho MVP.
    Scale thật sự bằng ONNX sẽ thay thế hàm này ở ai_engine.py
    """
    w, h = img.size
    # Bước 1: scale lên bằng NEAREST để giữ cứng pixel
    nearest = img.resize((w * scale, h * scale), Image.NEAREST)
    # Bước 2: sharpen nhẹ để cạnh rõ hơn
    from PIL import ImageFilter
    sharpened = nearest.filter(ImageFilter.SHARPEN)
    return sharpened


def upscale(image: Image.Image, scale: int = 2) -> ProcessResult:
    if scale not in (2, 4):
        return ProcessResult(False, None, "Scale chỉ hỗ trợ 2x hoặc 4x", image.size, (0, 0))

    ok, msg = validate(image)
    if not ok:
        return ProcessResult(False, None, msg, image.size, (0, 0))

    try:
        result = _xbrz_scale(image, scale)
        return ProcessResult(True, result, "OK", image.size, result.size)
    except Exception as e:
        return ProcessResult(False, None, f"Lỗi upscale: {e}", image.size, (0, 0))


def to_bytes(image: Image.Image, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


if __name__ == "__main__":
    # Test nhanh: tạo ảnh giả 16x16, upscale 4x, kiểm tra kích thước
    test_img = Image.new("RGBA", (16, 16), color=(106, 90, 205, 255))
    r = upscale(test_img, scale=4)
    print(f"Success : {r.success}")
    print(f"Input   : {r.input_size}")
    print(f"Output  : {r.output_size}")
    print(f"Message : {r.message}")
