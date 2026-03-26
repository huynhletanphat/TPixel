"""
core/benchmarker.py
Đo phần cứng thực tế, tính TPixel Score theo platform, đề xuất model.
Import bởi: ai_engine.py, server.py
"""

import os
import json
import time
import platform as _platform
import psutil
from dataclasses import dataclass, field
from typing import List
from core.platform_detector import detect, PlatformInfo


@dataclass
class ModelSuggestion:
    id     : str
    name   : str
    task   : str
    size_mb: int
    label  : str   # "optimal" | "ok" | "slow" | "unavailable"
    reason : str


@dataclass
class BenchmarkResult:
    platform_info : PlatformInfo
    ram_total_mb  : int
    ram_free_mb   : int
    cpu_count     : int
    cpu_score     : float
    gpu_available : bool
    tpixel_score  : int
    score_detail  : dict
    suggestions   : List[ModelSuggestion] = field(default_factory=list)


def _measure_cpu() -> float:
    try:
        import numpy as np
        size  = 512
        start = time.time()
        for _ in range(10):
            a = np.random.rand(size, size).astype("float32")
            np.dot(a, a.T)
        elapsed  = time.time() - start
        ops_mb   = (size * size * 4 * 10) / (1024 ** 2)
        return round(ops_mb / elapsed, 2)
    except Exception:
        return 0.0


def _detect_gpu() -> bool:
    try:
        import onnxruntime as ort
        return "CUDAExecutionProvider" in ort.get_available_providers()
    except Exception:
        return False


def _calc_score(info: PlatformInfo, ram_free_mb: int,
                cpu_score: float, cpu_count: int, gpu: bool) -> tuple[int, dict]:
    """
    Scoring riêng theo platform và chip architecture.
    Mỗi platform có ngưỡng thực tế khác nhau.
    """

    if info.platform == "termux" or info.is_mobile:
        # ARM mobile — ngưỡng thực tế của điện thoại
        ram_score  = min(ram_free_mb / 2048 * 35, 35)  # 2GB free = full
        cpu_score_ = min(cpu_score   / 25   * 30, 30)  # 25 MB/s = full
        core_score = min(cpu_count   / 8    * 15, 15)  # 8 core = full
        gpu_bonus  = 0                                  # GPU hiếm trên mobile
        arch_bonus = 5 if "aarch64" in info.architecture else 0  # ARM64 tốt hơn ARM32
        penalty    = 0

    elif info.platform == "linux":
        # x86 Linux — ngưỡng laptop/PC
        ram_score  = min(ram_free_mb / 6144 * 35, 35)  # 6GB free = full
        cpu_score_ = min(cpu_score   / 80   * 25, 25)  # 80 MB/s = full
        core_score = min(cpu_count   / 8    * 15, 15)
        gpu_bonus  = 20 if gpu else 0
        arch_bonus = 5 if "x86_64" in info.architecture else 0
        penalty    = 0

    elif info.platform == "windows":
        # Windows — tương tự Linux nhưng overhead cao hơn
        ram_score  = min(ram_free_mb / 6144 * 35, 35)
        cpu_score_ = min(cpu_score   / 70   * 25, 25)  # thấp hơn linux 1 chút
        core_score = min(cpu_count   / 8    * 15, 15)
        gpu_bonus  = 20 if gpu else 0
        arch_bonus = 0
        penalty    = -5  # Windows overhead

    else:
        ram_score  = min(ram_free_mb / 4096 * 35, 35)
        cpu_score_ = min(cpu_score   / 50   * 25, 25)
        core_score = min(cpu_count   / 8    * 15, 15)
        gpu_bonus  = 10 if gpu else 0
        arch_bonus = 0
        penalty    = 0

    total = int(ram_score + cpu_score_ + core_score + gpu_bonus + arch_bonus + penalty)
    total = max(0, min(100, total))

    detail = {
        "ram_score"  : round(ram_score, 1),
        "cpu_score"  : round(cpu_score_, 1),
        "core_score" : round(core_score, 1),
        "gpu_bonus"  : gpu_bonus,
        "arch_bonus" : arch_bonus,
        "penalty"    : penalty,
        "total"      : total,
    }
    return total, detail


def _label(model: dict, score: int) -> tuple[str, str]:
    """
    Đề xuất dựa trên score và size model.
    Không dùng platform để chặn — chỉ dùng để gợi ý.
    """
    size = model.get("size_mb", 0)

    if score >= 70:
        if size <= 200:   return "optimal", "Tối ưu cho máy này"
        if size <= 1000:  return "ok",      "Có thể dùng tốt"
        return "slow", f"Nặng {size}MB — sẽ chậm"

    elif score >= 40:
        if size <= 100:   return "optimal", "Tối ưu cho máy này"
        if size <= 500:   return "ok",      "Có thể dùng"
        return "slow", f"Nặng {size}MB — cần chờ"

    else:  # score < 40 — thiết bị yếu
        if size <= 50:    return "ok",      "Phù hợp thiết bị này"
        if size <= 200:   return "slow",    "Sẽ chậm nhưng chạy được"
        return "slow", f"Rất nặng cho thiết bị này — {size}MB"


def run(registry_path: str = "models/registry.json") -> BenchmarkResult:
    info      = detect()
    mem       = psutil.virtual_memory()
    ram_total = mem.total    // (1024 ** 2)
    ram_free  = mem.available // (1024 ** 2)
    cpu_count = psutil.cpu_count(logical=True) or 1
    cpu_speed = _measure_cpu()
    gpu       = _detect_gpu()
    score, detail = _calc_score(info, ram_free, cpu_speed, cpu_count, gpu)

    result = BenchmarkResult(
        platform_info = info,
        ram_total_mb  = ram_total,
        ram_free_mb   = ram_free,
        cpu_count     = cpu_count,
        cpu_score     = cpu_speed,
        gpu_available = gpu,
        tpixel_score  = score,
        score_detail  = detail,
    )

    with open(registry_path) as f:
        registry = json.load(f)

    for m in registry["models"]:
        label, reason = _label(m, score)
        result.suggestions.append(ModelSuggestion(
            id      = m["id"],
            name    = m["name"],
            task    = m["task"],
            size_mb = m["size_mb"],
            label   = label,
            reason  = reason,
        ))

    return result


if __name__ == "__main__":
    r = run()
    print(f"Platform : {r.platform_info.platform} ({r.platform_info.architecture})")
    print(f"Score    : {r.tpixel_score}/100")
    print(f"Detail   : {r.score_detail}")
    print(f"RAM      : {r.ram_free_mb}MB free / {r.ram_total_mb}MB total")
    print(f"CPU      : {r.cpu_score} MB/s | {r.cpu_count} cores")
    print(f"GPU      : {'Yes' if r.gpu_available else 'No'}")
    print()
    for s in r.suggestions:
        icon = {"optimal":"⭐","ok":"✓","slow":"⚠","unavailable":"✗"}[s.label]
        print(f"{icon} [{s.task:<8}] {s.name:<30} {s.size_mb}MB — {s.reason}")
