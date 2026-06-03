from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "CreativeStudio AI"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"

    DATABASE_URL: str = "postgresql+asyncpg://creativestudioai:Baguvix1%40@localhost:5432/creativestudioai"
    REDIS_URL: str = "redis://localhost:6379/0"

    SECRET_KEY: str = "change_me_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_HTTP_REFERER: str = "http://localhost:3000"
    OPENROUTER_MODEL_CLAUDE: str = "anthropic/claude-haiku-4.5"
    OPENROUTER_MODEL_CLAUDE_SCRIPT: str = "anthropic/claude-sonnet-4"
    OPENROUTER_MODEL_OPENAI: str = "openai/gpt-4o-mini"
    OPENROUTER_MODEL_IMAGE: str = "google/gemini-3.1-flash-image-preview"
    OPENROUTER_MODEL_VIDEO: str = "google/veo-3.1"

    # Runway ML — image + video (Veo) generation
    RUNWAYML_API_KEY: str = ""
    RUNWAYML_BASE_URL: str = "https://api.dev.runwayml.com/v1"
    RUNWAYML_API_VERSION: str = "2024-11-06"
    RUNWAYML_MODEL_IMAGE: str = "gemini_image3.1_flash"
    RUNWAYML_IMAGE_SIZE: str = "1K"
    RUNWAYML_MODEL_VIDEO: str = "veo3.1"
    RUNWAYML_IMAGE_RATIO: str = "1080:1080"
    RUNWAYML_VIDEO_RATIO: str = "1080:1920"
    RUNWAYML_VIDEO_DURATION: int = 8
    # Retry Runway when their API returns high-load / rate-limit (resubmits a new task)
    RUNWAYML_TRANSIENT_RETRY_ATTEMPTS: int = 3
    RUNWAYML_TRANSIENT_RETRY_BASE_SEC: float = 15.0
    RUNWAYML_VOICEOVER_ENABLED: bool = True
    # Scale/crop reel/video to full 1080x1920 (fixes HeyGen letterboxing)
    VIDEO_PORTRAIT_NORMALIZE: bool = True
    # Trim HeyGen/Runway output when longer than brief video_duration_seconds
    VIDEO_TRIM_TO_REQUESTED_DURATION: bool = True
    VIDEO_LOGO_REQUIRED: bool = True
    DEFAULT_VIDEO_LOGO_URL: str = ""
    CLICKTRENDS_LOGO_FILE: str = ""
    RUNWAYML_TTS_MODEL: str = "eleven_multilingual_v2"
    RUNWAYML_VOICE_PRESET: str = "Serene"

    IMAGE_GENERATION_PROVIDER: str = "nano-banana-2"
    VIDEO_GENERATION_PROVIDER: str = "veo-3.1"

    HEYGEN_API_KEY: str = ""
    HEYGEN_BASE_URL: str = "https://api.heygen.com"
    # v3 = Video Agent (dynamic scenes/backgrounds). v2 = flat-color talking head only.
    HEYGEN_VIDEO_API: str = "v3"
    HEYGEN_AVATAR_ID: str = ""
    HEYGEN_VOICE_ID: str = ""
    HEYGEN_AVATAR_OPTIONS: str = ""
    HEYGEN_VOICE_OPTIONS: str = ""
    HEYGEN_HTTP_RETRY_ATTEMPTS: int = 6
    HEYGEN_HTTP_RETRY_BASE_SEC: float = 2.0
    # Video Agent 30s ads often need 15–35 min; old 900s cap caused false "failed"
    HEYGEN_V3_POLL_MAX_WAIT_SECONDS: int = 3600
    HEYGEN_V1_POLL_MAX_WAIT_SECONDS: int = 1200

    # Higgsfield — https://platform.higgsfield.ai (API Key ID + Secret from cloud dashboard)
    HIGGSFIELD_API_KEY: str = ""
    HIGGSFIELD_API_SECRET: str = ""
    HIGGSFIELD_BASE_URL: str = "https://platform.higgsfield.ai"
    HIGGSFIELD_POLL_MAX_WAIT_SECONDS: int = 1800

    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    META_ACCESS_TOKEN: str = ""
    META_AD_ACCOUNT_ID: str = ""
    META_GRAPH_API_VERSION: str = "v21.0"

    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 52_428_800  # 50 MB

    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "admin123"

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


settings = Settings()
