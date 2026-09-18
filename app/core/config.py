from pydantic_settings import BaseSettings
from pydantic import SecretStr, Field
from typing import Literal


class Settings(BaseSettings):

    DATABASE_URL: str
    AI_SERVICE_URL: str
    AI_REQUEST_TIMEOUT_SECONDS: float = Field(default=15.0, gt=0, le=15)
    AI_CIRCUIT_FAILURE_THRESHOLD: int = Field(default=3, ge=1, le=100)
    AI_CIRCUIT_COOLDOWN_SECONDS: float = Field(default=30.0, gt=0, le=300)
    ENABLE_SAMPLE_SCAN: bool = False
    SAMPLE_IMAGES_DIR: str = "samples"
    SUPABASE_URL: str | None = None
    SUPABASE_JWT_SECRET: SecretStr | None = None
    SUPABASE_JWT_ALGORITHM: Literal["HS256", "ES256", "RS256"] = "HS256"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()