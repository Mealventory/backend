from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    DATABASE_URL: str
    AI_SERVICE_URL: str
    FIREBASE_PROJECT_ID: str | None = None

    model_config = {"env_file": ".env"}


settings = Settings()