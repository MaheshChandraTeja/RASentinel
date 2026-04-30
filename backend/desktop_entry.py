from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn


def configure_runtime_paths() -> None:
    """Keep source and frozen runtime imports consistent."""
    if getattr(sys, "frozen", False):
        runtime_root = Path(sys.executable).resolve().parent
    else:
        runtime_root = Path(__file__).resolve().parent

    if str(runtime_root) not in sys.path:
        sys.path.insert(0, str(runtime_root))


def main() -> None:
    configure_runtime_paths()

    # Import the ASGI app directly so PyInstaller can see and bundle the
    # backend package during analysis. Do not pass "app.main:app" as a string
    # here; string imports are the entire reason packaged builds were losing
    # the local app package like a clown car losing a wheel.
    from app.main import app as fastapi_app

    host = os.getenv("RASENTINEL_HOST", "127.0.0.1")
    port = int(os.getenv("RASENTINEL_PORT", "8000"))

    uvicorn.run(
        fastapi_app,
        host=host,
        port=port,
        reload=False,
        workers=1,
        log_level=os.getenv("RASENTINEL_UVICORN_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
