from fastapi import APIRouter

from app.api.v1 import admin, assets, auth, brands, briefs, generation, meta, performance, variants

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(brands.router)
api_router.include_router(briefs.router)
api_router.include_router(generation.router)
api_router.include_router(meta.router)
api_router.include_router(variants.router)
api_router.include_router(assets.router)
api_router.include_router(performance.router)
api_router.include_router(admin.router)
