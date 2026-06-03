from abc import ABC, abstractmethod


class ImageGenerationProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        *,
        prompt: str,
        tenant_id: str,
        model: str,
        format_type: str,
        logo_url: str | None = None,
        logo_on_light_url: str | None = None,
    ) -> dict:
        raise NotImplementedError


class VideoGenerationProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        *,
        prompt: str,
        brief: dict,
        copy: dict,
        format_type: str,
        model: str,
        tenant_id: str,
        source_image_url: str | None = None,
        duration_seconds: int | None = None,
    ) -> dict:
        raise NotImplementedError
