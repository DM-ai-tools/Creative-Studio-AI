from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal, create_tables
from app.services.bootstrap_service import ensure_default_admin
from app.services.media_content import sniff_media_type

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

upload_dir = Path(settings.UPLOAD_DIR).resolve()


@app.on_event("startup")
async def on_startup():
    from app.services.ffmpeg_util import ffmpeg_executable

    upload_path = Path(settings.UPLOAD_DIR)
    upload_path.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_executable()
    if ff:
        import logging

        logging.getLogger(__name__).info("ffmpeg ready for logo/subtitle burn-in: %s", ff)
    else:
        import logging

        logging.getLogger(__name__).warning(
            "ffmpeg NOT found — HeyGen videos will save without logo or burned-in captions. "
            "Run: pip install imageio-ffmpeg (in backend/), then restart."
        )
    await create_tables()
    async with AsyncSessionLocal() as db:
        await ensure_default_admin(db)


@app.get("/files/{file_path:path}", include_in_schema=False)
async def serve_upload(file_path: str):
    """Serve uploads with Content-Type from file bytes (fixes JPEG saved as .png)."""
    resolved = (upload_dir / file_path).resolve()
    try:
        resolved.relative_to(upload_dir)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found") from None
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    header = resolved.read_bytes()[:32]
    media_type = sniff_media_type(header, fallback_path=resolved)
    return FileResponse(
        resolved,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "version": settings.APP_VERSION, "env": settings.APP_ENV}


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(status_code=404, content={"detail": "Not found"})


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
