import logging
import sqlite3
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from nicegui import ui

from culturebridge.api.router import router
from culturebridge.config import get_settings
from culturebridge.database import initialize_database
from culturebridge.services.operation_service import OperationBusyError
from culturebridge.services.session_service import AnonymousSessionMiddleware
from culturebridge.ui.pages import register_pages

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.public_mode and (
        settings.storage_secret == "culturebridge-local-development"
        or len(settings.storage_secret) < 32
    ):
        raise RuntimeError("공개 모드는 별도의 32자 이상 운영용 STORAGE_SECRET이 필요합니다.")
    initialize_database()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI Agent 기반 국가별 문화유산 비교 탐구 교육 플랫폼",
    lifespan=lifespan,
)
app.include_router(router)
app.add_middleware(AnonymousSessionMiddleware)


@app.exception_handler(OperationBusyError)
async def learning_busy_handler(_: Request, exc: OperationBusyError):
    return JSONResponse(status_code=429, content={"detail": str(exc)}, headers={"Retry-After": "5"})


@app.exception_handler(sqlite3.Error)
async def database_error_handler(_: Request, exc: sqlite3.Error) -> JSONResponse:
    logging.getLogger(__name__).error("Database operation failed: %s", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": "자료를 저장하거나 불러올 수 없습니다. 잠시 후 다시 시도해 주세요."},
    )


register_pages()
ui.run_with(
    app,
    title=settings.app_name,
    storage_secret=settings.storage_secret,
    favicon="🌏",
)


def run() -> None:
    uvicorn.run(
        "culturebridge.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ in {"__main__", "__mp_main__"}:
    run()
