from http import HTTPStatus
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class AuthProblem(HTTPException):
    def __init__(self, status_code: int, detail: str):
        super().__init__(status_code, detail,
                         headers={"WWW-Authenticate": "Bearer"} if status_code == 401 else None)


async def auth_problem_handler(request: Request, exc: AuthProblem):
    return JSONResponse(
        status_code=exc.status_code,
        content={"type": "about:blank", "title": HTTPStatus(exc.status_code).phrase,
                 "status": exc.status_code, "detail": exc.detail, "instance": request.url.path},
        headers=exc.headers, media_type="application/problem+json",
    )


PROBLEM_SCHEMA = {
    "type": "object",
    "required": ["type", "title", "status", "detail", "instance"],
    "properties": {name: {"type": "integer" if name == "status" else "string"}
                   for name in ("type", "title", "status", "detail", "instance")},
}
AUTH_RESPONSES = {
    code: {"description": HTTPStatus(code).phrase,
           "content": {"application/problem+json": {"schema": PROBLEM_SCHEMA}}}
    for code in (400, 401, 403, 503)
}
