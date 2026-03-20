"""
core/model_manager.py
Quản lý model: liệt kê, tải về, kiểm tra, xóa.
Import bởi: server.py
"""

import os
import json
import threading
import requests
from dataclasses import dataclass, field
from typing import Dict, Optional


REGISTRY_PATH  = "models/registry.json"
DOWNLOAD_DIR   = "models/downloaded"


@dataclass
class DownloadProgress:
    model_id   : str
    status     : str        # "pending" | "downloading" | "done" | "error"
    percent    : float      # 0.0 - 100.0
    size_total : int        # bytes
    size_done  : int        # bytes
    message    : str        # mô tả trạng thái hoặc lỗi


# Dict lưu tiến trình tải — server.py poll cái này mỗi giây
_progress: Dict[str, DownloadProgress] = {}


def load_registry() -> list:
    with open(REGISTRY_PATH) as f:
        return json.load(f)["models"]


def get_all() -> list:
    """Trả về toàn bộ model + trạng thái đã tải chưa."""
    models = load_registry()
    for m in models:
        m["downloaded"] = is_downloaded(m["id"])
        m["progress"]   = _progress.get(m["id"])
    return models


def get_by_id(model_id: str) -> Optional[dict]:
    for m in load_registry():
        if m["id"] == model_id:
            m["downloaded"] = is_downloaded(model_id)
            return m
    return None


def is_downloaded(model_id: str) -> bool:
    path = _model_path(model_id)
    return os.path.exists(path) and os.path.getsize(path) > 0


def _model_path(model_id: str) -> str:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    return os.path.join(DOWNLOAD_DIR, f"{model_id}.onnx")


def get_progress(model_id: str) -> Optional[DownloadProgress]:
    return _progress.get(model_id)


def _download_worker(model: dict):
    """Chạy trong thread riêng — không block server."""
    mid = model["id"]
    url = model["download_url"]
    dst = _model_path(mid)

    _progress[mid] = DownloadProgress(
        model_id=mid, status="downloading",
        percent=0.0, size_total=0, size_done=0,
        message="Đang kết nối..."
    )

    try:
        resp = requests.get(url, stream=True, timeout=30)
        if resp.status_code != 200:
            _progress[mid].status  = "error"
            _progress[mid].message = f"HTTP {resp.status_code}"
            return

        total = int(resp.headers.get("content-length", 0))
        _progress[mid].size_total = total
        _progress[mid].message    = "Đang tải..."

        done = 0
        with open(dst, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
                    _progress[mid].size_done = done
                    _progress[mid].percent   = (
                        round(done / total * 100, 1) if total else 0.0
                    )

        _progress[mid].status  = "done"
        _progress[mid].percent = 100.0
        _progress[mid].message = "Tải xong"

    except Exception as e:
        # Xóa file dở nếu bị lỗi giữa chừng
        if os.path.exists(dst):
            os.remove(dst)
        _progress[mid].status  = "error"
        _progress[mid].message = str(e)


def start_download(model_id: str) -> tuple[bool, str]:
    """Bắt đầu tải model trong background thread."""
    # Đã tải rồi thì không tải lại
    if is_downloaded(model_id):
        return False, "Model đã tải sẵn"

    # Đang tải thì không tải lại
    prog = _progress.get(model_id)
    if prog and prog.status == "downloading":
        return False, "Đang tải..."

    model = get_by_id(model_id)
    if not model:
        return False, f"Không tìm thấy model '{model_id}'"

    t = threading.Thread(target=_download_worker, args=(model,), daemon=True)
    t.start()
    return True, "Bắt đầu tải"


def delete_model(model_id: str) -> tuple[bool, str]:
    path = _model_path(model_id)
    if not os.path.exists(path):
        return False, "Model chưa được tải"
    os.remove(path)
    _progress.pop(model_id, None)
    return True, "Đã xóa"


if __name__ == "__main__":
    models = get_all()
    for m in models:
        status = "✓" if m["downloaded"] else "✗"
        print(f"{status} [{m['task']:<8}] {m['id']:<35} {m['size_mb']}MB")
