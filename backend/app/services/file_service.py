import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings


class FileService:
    def __init__(self):
        self.upload_dir = Path(settings.UPLOAD_DIR)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def save_file(
        self,
        file: UploadFile,
        tenant_id: str,
        subfolder: str = "assets",
    ) -> dict:
        content = await file.read()
        if len(content) > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Max {settings.MAX_UPLOAD_SIZE // 1_048_576} MB.",
            )

        suffix = Path(file.filename or "file").suffix.lower()
        unique_name = f"{uuid.uuid4()}{suffix}"
        dest_dir = self.upload_dir / tenant_id / subfolder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / unique_name

        with open(dest_path, "wb") as f:
            f.write(content)

        rel_path = str(dest_path.relative_to(self.upload_dir))
        return {
            "file_name": file.filename,
            "file_path": str(dest_path),
            "file_url": f"/files/{rel_path.replace(chr(92), '/')}",
            "file_size": len(content),
            "file_type": file.content_type or "application/octet-stream",
        }

    def save_bytes(
        self,
        content: bytes,
        tenant_id: str,
        subfolder: str,
        suffix: str,
        content_type: str,
    ) -> dict:
        unique_name = f"{uuid.uuid4()}{suffix}"
        dest_dir = self.upload_dir / tenant_id / subfolder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / unique_name

        with open(dest_path, "wb") as f:
            f.write(content)

        rel_path = str(dest_path.relative_to(self.upload_dir))
        return {
            "file_name": unique_name,
            "file_path": str(dest_path),
            "file_url": f"/files/{rel_path.replace(chr(92), '/')}",
            "file_size": len(content),
            "file_type": content_type,
        }

    async def delete_file(self, file_path: str) -> None:
        path = Path(file_path)
        if path.exists() and path.is_file():
            path.unlink()

    def get_file_url(self, file_path: str) -> str:
        rel = Path(file_path).relative_to(self.upload_dir)
        return f"/files/{str(rel).replace(chr(92), '/')}"


file_service = FileService()
