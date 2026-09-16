"""Verify Supabase access tokens; never accept a token-selected algorithm or URL."""
from functools import lru_cache
from uuid import UUID
import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWTError
from app.core.config import settings
from app.core.auth_errors import AuthProblem


@lru_cache(maxsize=4)
def jwks_client(issuer: str):
    return PyJWKClient(issuer + "/.well-known/jwks.json", timeout=5)


def verify_supabase_token(token: str) -> dict:
    if not settings.SUPABASE_URL:
        raise AuthProblem(503, "Authentication is not configured")
    issuer = settings.SUPABASE_URL.rstrip("/") + "/auth/v1"
    algorithm = settings.SUPABASE_JWT_ALGORITHM
    try:
        if jwt.get_unverified_header(token).get("alg") != algorithm:
            raise jwt.InvalidAlgorithmError("Unexpected signing algorithm")
        if algorithm == "HS256":
            if not settings.SUPABASE_JWT_SECRET:
                raise AuthProblem(503, "Authentication is not configured")
            key = settings.SUPABASE_JWT_SECRET.get_secret_value()
        else:
            key = jwks_client(issuer).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token, key, algorithms=[algorithm], issuer=issuer, audience="authenticated",
            options={"require": ["exp", "iat", "sub", "iss", "aud", "role"]},
        )
        if claims["role"] != "authenticated":
            raise jwt.InvalidTokenError("Not a user access token")
        claims["sub"] = str(UUID(claims["sub"]))
        return claims
    except PyJWKClientConnectionError:
        raise AuthProblem(503, "Authentication provider unavailable") from None
    except (PyJWTError, ValueError, TypeError, AttributeError):
        raise AuthProblem(401, "Invalid or expired bearer token") from None
