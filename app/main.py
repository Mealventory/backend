from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.core.auth_errors import (
    AuthProblem,
    http_problem_handler,
    validation_problem_handler,
)
from app.core.config import settings


app = FastAPI(
    title="Mealventory API",
    version="1.0.0",
)

app.add_exception_handler(StarletteHTTPException, http_problem_handler)
app.add_exception_handler(AuthProblem, http_problem_handler)
app.add_exception_handler(RequestValidationError, validation_problem_handler)

# Explicit origins support credentialed web requests; development wildcard does not.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials="*" not in settings.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
def health_check():
    return {"status": "API running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
