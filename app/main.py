from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.router import api_router
from app.core.config import settings
from app.core.auth_errors import AuthProblem, auth_problem_handler


app = FastAPI(
    title="Mealventory API",
    version="1.0.0",
)

app.add_exception_handler(AuthProblem, auth_problem_handler)

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