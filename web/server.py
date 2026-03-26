"""
web/server.py
FastAPI server — cổng giao tiếp giữa UI và core
Chạy: uvicorn web.server:app --host 0.0.0.0 --port 8000 --reload
"""

import os
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from core.ai_engine import init, get_state, scale, generate, set_model
from core.model_manager import (
    get_all, get_by_id, get_progress,
    start_download, delete_model, is_downloaded
)


# ── Auth ──────────────────────────────────────────────────────────
TOKEN_FILE = "data/.token"

def _get_token() -> str:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(TOKEN_FILE):
        open(TOKEN_FILE, "w").write(secrets.token_urlsafe(16))
    return open(TOKEN_FILE).read().strip()

api_key_header = APIKeyHeader(name="X-Token", auto_error=False)

async def verify(token: str = Depends(api_key_header)):
    if token != _get_token():
        raise HTTPException(status_code=403, detail="Invalid token")
    return token


# ── Lifespan ──────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init()
    print(f"\n🔑 Token : {_get_token()}")
    print(f"🌐 Open  : http://localhost:8000\n")
    yield


app = FastAPI(title="TPixel", version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="web/static"), name="static")


# ── UI ────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    with open("web/templates/index.html") as f:
        return f.read()


# ── System ───────────────────────────────────────────────────────
@app.get("/api/status")
async def status():
    state = get_state()
    return {
        "platform"     : state.platform.platform,
        "tpixel_score" : state.benchmark.tpixel_score,
        "mode"         : state.mode,
        "active_model" : state.active_model,
        "ram_free_mb"  : state.benchmark.ram_free_mb,
        "ram_total_mb" : state.benchmark.ram_total_mb,
    }


# ── Model Manager ─────────────────────────────────────────────────
@app.get("/api/models")
async def models():
    """Toàn bộ model + trạng thái downloaded + progress."""
    return get_all()


@app.get("/api/models/{model_id}")
async def model_detail(model_id: str):
    m = get_by_id(model_id)
    if not m:
        raise HTTPException(status_code=404, detail="Model không tồn tại")
    return m


@app.post("/api/models/{model_id}/download")
async def download(model_id: str):
    """Bắt đầu tải model trong background. Poll /progress để theo dõi."""
    ok, msg = start_download(model_id)
    if not ok and "đã tải" not in msg:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}


@app.get("/api/models/{model_id}/progress")
async def progress(model_id: str):
    """Poll endpoint — frontend gọi mỗi giây khi đang tải."""
    prog = get_progress(model_id)
    if not prog:
        downloaded = is_downloaded(model_id)
        return {
            "status" : "done" if downloaded else "idle",
            "percent": 100.0  if downloaded else 0.0,
            "message": "Đã tải sẵn" if downloaded else "Chưa tải",
        }
    return {
        "status"    : prog.status,
        "percent"   : prog.percent,
        "size_total": prog.size_total,
        "size_done" : prog.size_done,
        "message"   : prog.message,
    }


@app.delete("/api/models/{model_id}")
async def delete(model_id: str):
    ok, msg = delete_model(model_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}


class SelectModel(BaseModel):
    model_id: str

@app.post("/api/models/select")
async def select_model(body: SelectModel):
    ok, msg = set_model(body.model_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}


# ── Scale ─────────────────────────────────────────────────────────
@app.post("/api/scale")
async def scale_image(file: UploadFile = File(...), factor: int = 2, method: str = "nearest"):
    if factor not in (2, 4):
        raise HTTPException(status_code=400, detail="Factor chỉ hỗ trợ 2 hoặc 4")
    if method not in ("nearest", "sharp", "ai"):
        raise HTTPException(status_code=400, detail="Method: nearest | sharp | ai")
    data = await file.read()
    ok, result, msg = scale(data, factor, method)
    if not ok:
        raise HTTPException(status_code=422, detail=msg)
    return Response(content=result, media_type="image/png", headers={"X-Scale-Info": msg.encode("ascii", errors="replace").decode("ascii")})


# ── Generate ──────────────────────────────────────────────────────
class GenRequest(BaseModel):
    prompt: str

@app.post("/api/generate")
async def generate_image(body: GenRequest):
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt không được trống")
    ok, result, msg = generate(body.prompt)
    if not ok:
        raise HTTPException(status_code=500, detail=msg)
    return Response(content=result, media_type="image/png")


@app.get("/api/system")
async def system_stats():
    import psutil, shutil
    cpu  = psutil.cpu_percent(interval=None) or psutil.cpu_percent(interval=0.5)
    mem  = psutil.virtual_memory()
    disk = shutil.disk_usage("/")
    return {
        "cpu_percent"  : cpu,
        "ram_percent"  : mem.percent,
        "ram_used_mb"  : mem.used     // (1024**2),
        "ram_total_mb" : mem.total    // (1024**2),
        "ram_free_mb"  : mem.available // (1024**2),
        "disk_used_gb" : round(disk.used  / (1024**3), 1),
        "disk_total_gb": round(disk.total / (1024**3), 1),
        "disk_percent" : round(disk.used  / disk.total * 100, 1),
    }


@app.get("/api/benchmark")
async def benchmark_detail():
    state = get_state()
    return {
        "cpu_score"   : state.benchmark.cpu_score,
        "cpu_count"   : state.benchmark.cpu_count,
        "gpu"         : state.benchmark.gpu_available,
        "architecture": state.benchmark.platform_info.architecture,
        "score_detail": state.benchmark.score_detail,
    }
