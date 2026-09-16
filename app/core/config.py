from pydantic_settings import BaseSettings
from pydantic import SecretStr
from typing import Literal


class Settings(BaseSettings):

    DATABASE_URL: str
    AI_SERVICE_URL: str
    ENABLE_SAMPLE_SCAN: bool = False
    SAMPLE_IMAGES_DIR: str = "samples"
    SUPABASE_URL: str | None = None
    SUPABASE_JWT_SECRET: SecretStr | None = None
    SUPABASE_JWT_ALGORITHM: Literal["HS256", "ES256", "RS256"] = "HS256"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()