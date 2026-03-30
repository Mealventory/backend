from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    DATABASE_URL: str
    AI_SERVICE_URL: str
    ENABLE_SAMPLE_SCAN: bool = False
    SAMPLE_IMAGES_DIR: str = "samples"
    FIREBASE_PROJECT_ID: str | None = None

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()