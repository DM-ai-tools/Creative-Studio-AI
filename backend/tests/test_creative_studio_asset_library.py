"""Generated Creative Studio image library registration tests."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from PIL import Image

from app.api.v1.assets import RegisterGeneratedAssetRequest, register_generated_asset
from app.services.file_service import file_service


@pytest.mark.asyncio
async def test_generated_asset_registration_rejects_another_tenant(tmp_path, monkeypatch):
    monkeypatch.setattr(file_service, "upload_dir", str(tmp_path))
    user = SimpleNamespace(tenant_id=uuid4(), id=uuid4())
    data = RegisterGeneratedAssetRequest(file_url=f"/files/{uuid4()}/generated/frame.png")

    with pytest.raises(HTTPException, match="Only images generated in this workspace") as exc:
        await register_generated_asset(data, current_user=user, db=AsyncMock())

    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_generated_image_is_registered_as_reusable_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(file_service, "upload_dir", str(tmp_path))
    tenant_id = uuid4()
    user = SimpleNamespace(tenant_id=tenant_id, id=uuid4())
    image_path = Path(tmp_path) / str(tenant_id) / "generated" / "frame.png"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (32, 48), "red").save(image_path)
    file_url = f"/files/{tenant_id}/generated/frame.png"

    empty_result = Mock()
    empty_result.scalar_one_or_none.return_value = None
    db = SimpleNamespace(
        execute=AsyncMock(return_value=empty_result),
        add=Mock(),
        flush=AsyncMock(),
        refresh=AsyncMock(),
    )
    data = RegisterGeneratedAssetRequest(
        file_url=file_url,
        file_name="Opening scene",
        metadata={"role": "storyboard"},
    )

    created = await register_generated_asset(data, current_user=user, db=db)

    assert created.file_url == file_url
    assert created.asset_type == "creative_studio_reference"
    assert created.width == 32 and created.height == 48
    assert created.asset_metadata["source"] == "creative_studio_generated"
    assert created.asset_metadata["reusable"] is True
    db.add.assert_called_once_with(created)

    existing_result = Mock()
    existing_result.scalar_one_or_none.return_value = created
    db.execute.return_value = existing_result
    again = await register_generated_asset(data, current_user=user, db=db)

    assert again is created
    assert db.add.call_count == 1
