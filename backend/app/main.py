"""The MoveIn API.

Run it with::

    uvicorn backend.app.main:app --reload --port 8000

In development the Vite dev server proxies ``/api`` here, so the browser only
ever talks to one origin and there is no CORS to configure.  In production the
React bundle is served from this same process, which keeps deployment to a
single container.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import fares, journeys, live, meta, network, stops, user
from .config import BACKEND_ROOT, REPO_ROOT, get_settings
from .engine.service import get_planner

settings = get_settings()

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Warm the planner before serving, so the first request is not slow."""
    try:
        get_planner(settings)
    except Exception as exc:  # pragma: no cover - reported by /api/health
        print(f"[movein] network not loaded yet: {exc}")
    yield


app = FastAPI(
    title="MoveIn",
    description=(
        "All-in-one public transport journey planning for Great Britain. "
        "MoveIn combines bus, coach, rail, tram, metro and on-demand services "
        "into one search, prices the tickets a traveller actually has to buy, "
        "and ranks the results by what they care about."
    ),
    version=settings.version,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# The dev server runs on its own port, so allow local origins.  Credentials are
# not used: Phase 1 identities are client-generated device keys.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_timing_header(request: Request, call_next):  # type: ignore[no-untyped-def]
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-MoveIn-Duration-Ms"] = f"{(time.perf_counter() - started) * 1000:.1f}"
    return response


api_prefix = "/api"
app.include_router(meta, prefix=api_prefix)
app.include_router(stops, prefix=api_prefix)
app.include_router(journeys, prefix=api_prefix)
app.include_router(network, prefix=api_prefix)
app.include_router(fares, prefix=api_prefix)
app.include_router(live, prefix=api_prefix)
app.include_router(user, prefix=api_prefix)


@app.get("/api", include_in_schema=False)
def api_root() -> dict:
    return {
        "name": settings.app_name,
        "version": settings.version,
        "docs": "/api/docs",
        "endpoints": [
            "GET  /api/health",
            "GET  /api/preferences",
            "GET  /api/data-sources",
            "GET  /api/stops/search?q=",
            "GET  /api/stops/nearby?lat=&lon=",
            "GET  /api/stops/{stop_id}",
            "GET  /api/stops/regions",
            "POST /api/journeys/search",
            "POST /api/journeys/compare-emissions",
            "GET  /api/network/summary",
            "GET  /api/network/routes",
            "GET  /api/network/operators",
            "GET  /api/fares/products",
            "GET  /api/live/vehicles",
            "GET  /api/live/alerts",
            "POST /api/live/track",
            "GET  /api/me/saved",
            "POST /api/me/saved",
            "GET  /api/me/alerts",
            "POST /api/me/alerts",
            "GET  /api/me/alerts/check",
            "GET  /api/me/history",
        ],
    }


@app.exception_handler(ValueError)
async def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ---------------------------------------------------------------------------
# The built frontend, when it exists
# ---------------------------------------------------------------------------

if FRONTEND_DIST.exists():
    app.mount(
        "/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets"
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):  # type: ignore[no-untyped-def]
        """Serve the single-page app, letting the client router own the paths."""
        if full_path.startswith("api"):
            return JSONResponse(status_code=404, content={"detail": "not found"})
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(index)
        return JSONResponse(status_code=404, content={"detail": "frontend not built"})
else:
    @app.get("/", include_in_schema=False)
    def placeholder() -> dict:
        return {
            "message": (
                "MoveIn API is running. The web app is not built yet — run "
                "`npm install && npm run build` in frontend/, or `npm run dev` "
                "for the dev server."
            ),
            "api": "/api",
            "docs": "/api/docs",
            "frontend_dir": str(BACKEND_ROOT.parent / "frontend"),
        }


def run() -> None:  # pragma: no cover - convenience entry point
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )


if __name__ == "__main__":  # pragma: no cover
    run()
