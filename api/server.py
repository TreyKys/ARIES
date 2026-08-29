from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os

from api.routes import router
from api.ws_hub import router as ws_router

def create_app(engine, ws_hub, database) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        yield
        # Shutdown
        await engine.stop()

    app = FastAPI(title='ARES-1 Trading Engine API', lifespan=lifespan)
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.engine = engine
    app.state.ws_hub = ws_hub
    app.state.database = database

    app.include_router(router)
    app.include_router(ws_router)
    
    os.makedirs("dashboard", exist_ok=True)
    if not os.path.exists("dashboard/index.html"):
        with open("dashboard/index.html", "w") as f:
            f.write("<html><body><h1>ARES-1 Dashboard</h1></body></html>")

    app.mount("/static", StaticFiles(directory="dashboard"), name="dashboard")

    @app.get("/")
    async def root():
        return FileResponse("dashboard/index.html")

    return app
