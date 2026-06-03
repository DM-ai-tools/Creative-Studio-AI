from app.services.media.base import ImageGenerationProvider, VideoGenerationProvider
from app.services.media.heygen_provider import HeyGenVideoProvider, is_heygen_video_model
from app.services.media.higgsfield_models import (
    is_higgsfield_image_model,
    is_higgsfield_video_model,
)
from app.services.media.higgsfield_providers import (
    HiggsfieldImageProvider,
    HiggsfieldVideoProvider,
)
from app.services.media.runway_providers import RunwayImageProvider, RunwayVideoProvider

_image_providers: dict[str, ImageGenerationProvider] = {}
_video_providers: dict[str, VideoGenerationProvider] = {}


def get_image_provider(model: str | None = None) -> ImageGenerationProvider:
    if is_higgsfield_image_model(model):
        if "higgsfield" not in _image_providers:
            _image_providers["higgsfield"] = HiggsfieldImageProvider()
        return _image_providers["higgsfield"]
    if "runway" not in _image_providers:
        _image_providers["runway"] = RunwayImageProvider()
    return _image_providers["runway"]


def get_video_provider(model: str | None = None) -> VideoGenerationProvider:
    if is_heygen_video_model(model):
        if "heygen" not in _video_providers:
            _video_providers["heygen"] = HeyGenVideoProvider()
        return _video_providers["heygen"]
    if is_higgsfield_video_model(model):
        if "higgsfield" not in _video_providers:
            _video_providers["higgsfield"] = HiggsfieldVideoProvider()
        return _video_providers["higgsfield"]
    if "runway" not in _video_providers:
        _video_providers["runway"] = RunwayVideoProvider()
    return _video_providers["runway"]
