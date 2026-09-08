from __future__ import annotations

import uvicorn

from .config import get_settings


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "openresearchgraph.api.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
