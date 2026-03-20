"""
core/ai_engine.py
Điều phối trung tâm — gọi runner.py để inference ONNX thật.
Import bởi: server.py
"""

import io
import os
from PIL import Image
from dataclasses import dataclass
from core.platform_detector import detect, PlatformInfo
from core.benchmarker import run as run_benchmark, BenchmarkResult
from core.processors import load_image, to_bytes
from core.runner import run_scale
from core.model_manager import is_downloaded, get_by_id

MODE_LOCAL = "local"
MODE_API   = "api"

DOWNLOAD_DIR = "models/downloaded"


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
    mode = MODE_API if (platform.is_mobile or benchmark.tpixel_score < 30) else MODE_LOCAL
    _state = EngineState(
        platform=platform, benchmark=benchmark,
        mode=mode, active_model=None
    )
    return _state


def get_state() -> EngineState:
    if _state is None:
        return init()
    return _state


def set_model(model_id: str) -> tuple[bool, str]:
    state = get_state()
    ids = [m.id for m in state.benchmark.suggestions]
    if model_id not in ids:
        return False, f"Model '{model_id}' không có trong registry"
    state.active_model = model_id
    return True, f"Đã chọn model: {model_id}"


def _get_model_path(model_id: str | None, task: str) -> tuple[bool, str, str]:
    """
    Tìm model path theo thứ tự:
    1. active_model nếu có và đúng task
    2. Model đầu tiên đã tải phù hợp task
    3. Không có → báo lỗi rõ ràng
    """
    state = get_state()

    # Thử active model trước
    if model_id and is_downloaded(model_id):
        m = get_by_id(model_id)
        if m and m["task"] == task:
            return True, os.path.join(DOWNLOAD_DIR, f"{model_id}.onnx"), model_id

    # Tìm model đầu tiên đã tải đúng task
    for m in state.benchmark.suggestions:
        if m.task == task and is_downloaded(m.id):
            path = os.path.join(DOWNLOAD_DIR, f"{m.id}.onnx")
            return True, path, m.id

    return False, "", f"Chưa có model '{task}' nào được tải — vào Settings để tải"


def scale(image_bytes: bytes, factor: int = 2) -> tuple[bool, bytes, str]:
    ok, img, msg = load_image(image_bytes)
    if not ok:
        return False, b"", msg

    state = get_state()
    found, path, model_id = _get_model_path(state.active_model, "scale")

    if not found:
        return False, b"", path  # path chứa error message

    result = run_scale(path, img)
    if not result.success:
        return False, b"", result.message

    return True, to_bytes(result.image), model_id


def generate(prompt: str) -> tuple[bool, bytes, str]:
    """Generate chưa có model ONNX thật — trả về thông báo rõ ràng."""
    state = get_state()
    found, path, model_id = _get_model_path(state.active_model, "generate")
    if not found:
        return False, b"", "Chưa có model generate — vào Settings tải SD hoặc SDXL"
    # TODO: inference generate sau khi có runner_generate.py
    return False, b"", "Generate ONNX đang phát triển — coming soon"


if __name__ == "__main__":
    state = init()
    print(f"Mode         : {state.mode}")
    print(f"TPixel Score : {state.benchmark.tpixel_score}/100")
    print(f"Platform     : {state.platform.platform}")

    test_img = Image.new("RGB", (64, 64), color=(106, 90, 205))
    buf = io.BytesIO()
    test_img.save(buf, format="PNG")

    ok, result_bytes, msg = scale(buf.getvalue(), factor=4)
    print(f"Scale test   : {'OK' if ok else 'FAIL'} — {msg}")
    if ok:
        out = Image.open(io.BytesIO(result_bytes))
        print(f"Output size  : {out.size}")
