from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from server.routers import common, login, mys_api, rag


def create_app() -> FastAPI:
    app = FastAPI(title="米游社收藏夹 RAG 服务", version="1.0.0")

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):
        print(f"[422] {request.url} body validation error: {exc.errors()}")
        return JSONResponse(status_code=422, content={"detail": str(exc.errors())})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/static", StaticFiles(directory="static"), name="static")

    app.include_router(common.router)
    app.include_router(login.router)
    app.include_router(mys_api.router)
    app.include_router(rag.router)

    return app
