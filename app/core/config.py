from pydantic_settings import BaseSettings, NoDecode
from pydantic import SecretStr, Field, field_validator
from typing import Literal, Annotated
from urllib.parse import urlsplit


class Settings(BaseSettings):

    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])

    @field_validator('CORS_ORIGINS', mode='before')
    @classmethod
    def parse_cors_origins(cls, value):
        origins = value.split(',') if isinstance(value, str) else value
        result = []
        for origin in origins:
            origin = origin.strip()
            if not origin:
                continue
            if origin != '*':
                parsed = urlsplit(origin)
                if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                        or parsed.username is not None or parsed.password is not None
                        or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                        or '*' in origin or any(c.isspace() for c in origin)):
                    raise ValueError('CORS_ORIGINS must contain HTTP(S) origins without paths or wildcards')
                port = parsed.port  # Reject invalid ports.
                host = parsed.hostname.lower()
                if ':' in host:
                    host = f'[{host}]'
                suffix = f':{port}' if port is not None and (parsed.scheme, port) not in (('http', 80), ('https', 443)) else ''
                origin = f'{parsed.scheme}://{host}{suffix}'
            if origin not in result:
                result.append(origin)
        if '*' in result and len(result) != 1:
            raise ValueError('Use either * for development or explicit origins, not both')
        return result

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

    # Protected cron/job trigger for expiry notification delivery.
    NOTIFICATION_JOB_SECRET: SecretStr | None = None
    # Optional when Expo push security is enabled for the EAS project.
    EXPO_PUSH_ACCESS_TOKEN: SecretStr | None = None
    EXPO_PUSH_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0, le=30)

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()