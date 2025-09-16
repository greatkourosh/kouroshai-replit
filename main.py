import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from kouroshai.modules.tasks.routes import router as tasks_router
from kouroshai.modules.codegen.routes import router as codegen_router
from kouroshai.modules.weather.routes import router as weather_router
from kouroshai.modules.chat.routes import router as chat_router
from kouroshai.core.database import initialize_database

# Setup logging (do this ONCE, in your main entry point)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger("azure").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

app = FastAPI(title="KouroshAI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router)
app.include_router(codegen_router)
app.include_router(weather_router)
app.include_router(chat_router)   # <-- add this line

@app.on_event("startup")
def _startup():
    initialize_database()

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    # Log and return a safe error response so the caller doesn't hang
    import logging
    logging.getLogger("uvicorn.error").exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "message": "An internal error occurred"}
    )

# catch‑all fallback for requests to non-existing routes
@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def fallback_route(full_path: str, request: Request):
    return JSONResponse(
        status_code=404,
        content={
            "error": "not_found",
            "message": "No route configured for this path. Check server routes.",
            "path": full_path
        },
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)