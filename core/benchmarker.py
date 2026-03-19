"""
core/benchmarker.py
Đo phần cứng thực tế, tính TPixel Score, đề xuất model từ registry.json
Import bởi: ai_engine.py, server.py
"""

import os
import json
import time
import psutil
from dataclasses import dataclass, field
from typing import List
from core.platform_detector import detect, PlatformInfo


@dataclass
class ModelSuggestion:
    id         : str
    name       : str
    task       : str
    size_mb    : int
    label      : str  # "optimal" | "ok" | "slow" | "unavailable"
    reason     : str


@dataclass
class BenchmarkResult:
    platform_info  : PlatformInfo
    ram_total_mb   : int
    ram_free_mb    : int
    cpu_score      : float  # MB/s xử lý thực tế
    tpixel_score   : int    # 0-100
    suggestions    : List[ModelSuggestion] = field(default_factory=list)


def _measure_cpu_speed() -> float:
    # Tạo và xử lý mảng numpy để đo tốc độ CPU thực tế
    try:
        import numpy as np
        size = 512
        start = time.time()
        for _ in range(10):
            a = np.random.rand(size, size).astype("float32")
            b = np.dot(a, a.T)
        elapsed = time.time() - start
        ops_mb = (size * size * 4 * 10) / (1024 ** 2)
        return round(ops_mb / elapsed, 2)
    except Exception:
        return 0.0


def _calc_score(ram_free_mb: int, cpu_speed: float, is_mobile: bool) -> int:
    ram_score = min(ram_free_mb / 8192 * 50, 50)   # tối đa 50 điểm
    cpu_score = min(cpu_speed  / 200   * 40, 40)   # tối đa 40 điểm
    mobile_penalty = -10 if is_mobile else 0
    return max(0, min(100, int(ram_score + cpu_score + mobile_penalty)))


def _label(model: dict, ram_free_mb: int, score: int) -> tuple:
    if model["platform_info_platform"] not in model.get("platforms", []):
        return "unavailable", "Không hỗ trợ nền tảng này"
    if ram_free_mb < model["min_ram_mb"]:
        return "unavailable", f"Cần tối thiểu {model['min_ram_mb']}MB RAM"
    if ram_free_mb < model["recommended_ram_mb"]:
        return "slow", f"Nên có {model['recommended_ram_mb']}MB RAM để mượt"
    if score >= 60 and ram_free_mb >= model["recommended_ram_mb"]:
        return "optimal", "Tối ưu cho máy này"
    return "ok", "Có thể dùng"


def run(registry_path: str = "models/registry.json") -> BenchmarkResult:
    info       = detect()
    mem        = psutil.virtual_memory()
    ram_total  = mem.total  // (1024 ** 2)
    ram_free   = mem.available // (1024 ** 2)
    cpu_speed  = _measure_cpu_speed()
    score      = _calc_score(ram_free, cpu_speed, info.is_mobile)

    result = BenchmarkResult(
        platform_info = info,
        ram_total_mb  = ram_total,
        ram_free_mb   = ram_free,
        cpu_score     = cpu_speed,
        tpixel_score  = score,
    )

    with open(registry_path) as f:
        registry = json.load(f)

    for m in registry["models"]:
        m["platform_info_platform"] = info.platform
        label, reason = _label(m, ram_free, score)
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
    print(f"TPixel Score : {r.tpixel_score}/100")
    print(f"RAM Free     : {r.ram_free_mb}MB / {r.ram_total_mb}MB")
    print(f"CPU Speed    : {r.cpu_score} MB/s")
    print()
    for s in r.suggestions:
        icon = {"optimal":"⭐","ok":"✓","slow":"⚠","unavailable":"✗"}[s.label]
        print(f"{icon} [{s.task:<8}] {s.name:<25} {s.size_mb}MB — {s.reason}")
