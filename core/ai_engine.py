"""
core/ai_engine.py
Điều phối trung tâm.
Import bởi: server.py
"""

import io
import os
from PIL import Image
from dataclasses import dataclass
from core.platform_detector import detect, PlatformInfo
from core.benchmarker import run as run_benchmark, BenchmarkResult
from core.processors import load_image, to_bytes, upscale_nearest, upscale_sharp
from core.runner import run_scale
from core.model_manager import is_downloaded, get_by_id

DOWNLOAD_DIR = "models/downloaded"

# method constants
METHOD_NEAREST = "nearest"   # Pixel art — giữ cạnh vuông
METHOD_SHARP   = "sharp"     # Nearest + sharpen
METHOD_AI      = "ai"        # ONNX model


@dataclass
class EngineState:
    platform    : PlatformInfo
    benchmark   : BenchmarkResult
    mode        : str
    active_model: str | None


_state: EngineState | None = None


def init(registry_path: str = "models/registry.json") -> EngineState:
    global _state
    platform  = detect()
    benchmark = run_benchmark(registry_path)
    mode      = "api" if (platform.is_mobile or benchmark.tpixel_score < 30) else "local"
    _state    = EngineState(platform=platform, benchmark=benchmark,
                            mode=mode, active_model=None)
    return _state


def get_state() -> EngineState:
    if _state is None:
        return init()
    return _state


def set_model(model_id: str) -> tuple[bool, str]:
    state = get_state()
    ids   = [m.id for m in state.benchmark.suggestions]
    if model_id not in ids:
        return False, f"Model '{model_id}' không có trong registry"
    state.active_model = model_id
    return True, f"Đã chọn: {model_id}"


def _find_model(task: str) -> tuple[bool, str, str]:
    state = get_state()
    if state.active_model and is_downloaded(state.active_model):
        m = get_by_id(state.active_model)
        if m and m["task"] == task:
            return True, os.path.join(DOWNLOAD_DIR, f"{state.active_model}.onnx"), state.active_model
    for m in state.benchmark.suggestions:
        if m.task == task and is_downloaded(m.id):
            return True, os.path.join(DOWNLOAD_DIR, f"{m.id}.onnx"), m.id
    return False, "", f"Chưa có model '{task}' — vào Settings tải về"


def scale(image_bytes: bytes, factor: int = 2,
          method: str = METHOD_NEAREST) -> tuple[bool, bytes, str]:
    ok, img, msg = load_image(image_bytes)
    if not ok:
        return False, b"", msg

    # Nearest hoặc Sharp — không cần model
    if method == METHOD_NEAREST:
        r = upscale_nearest(img, factor)
        if not r.success:
            return False, b"", r.message
        return True, to_bytes(r.image), f"nearest {r.input_size}→{r.output_size}"

    if method == METHOD_SHARP:
        r = upscale_sharp(img, factor)
        if not r.success:
            return False, b"", r.message
        return True, to_bytes(r.image), f"sharp {r.input_size}→{r.output_size}"

    # AI — cần model ONNX
    found, path, model_id = _find_model("scale")
    if not found:
        return False, b"", path
    result = run_scale(path, img)
    if not result.success:
        return False, b"", result.message
    w, h = img.size
    ow, oh = result.image.size
    return True, to_bytes(result.image), f"{model_id} {w}x{h}→{ow}x{oh}"


def generate(prompt: str) -> tuple[bool, bytes, str]:
    return False, b"", "Generate đang phát triển — coming soon"


if __name__ == "__main__":
    state = init()
    print(f"Platform: {state.platform.platform} | Score: {state.benchmark.tpixel_score}/100")

    img = Image.new("RGB", (32, 32), (106, 90, 205))
    buf = io.BytesIO(); img.save(buf, format="PNG")

    for method in ["nearest", "sharp", "ai"]:
        ok, _, msg = scale(buf.getvalue(), factor=4, method=method)
        print(f"  {method:<8}: {'OK' if ok else 'FAIL'} — {msg}")
