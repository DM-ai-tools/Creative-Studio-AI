from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user
from app.schemas.meta import MetaExportRequest, MetaExportResponse, MetaStatusResponse
from app.services.meta.service import meta_service

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/status", response_model=MetaStatusResponse)
async def meta_status(current_user=Depends(get_current_user)):
  payload = await meta_service.verify()
  return MetaStatusResponse(**payload)


@router.post("/export", response_model=MetaExportResponse, status_code=status.HTTP_202_ACCEPTED)
async def export_to_meta(
  data: MetaExportRequest,
  current_user=Depends(get_current_user),
):
  if not data.variant_ids:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Select at least one variant")
  if not data.campaign_name.strip():
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campaign name is required")

  try:
    result = await meta_service.export_variants(
      tenant_id=current_user.tenant_id,
      variant_ids=data.variant_ids,
      campaign_name=data.campaign_name.strip(),
      ad_set_name=data.ad_set_name.strip() if data.ad_set_name else None,
    )
  except RuntimeError as exc:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

  return MetaExportResponse(**result)
