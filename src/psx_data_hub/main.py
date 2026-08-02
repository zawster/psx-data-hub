from __future__ import annotations

import uvicorn

from psx_data_hub.api.app import app
from psx_data_hub.core.config import settings


def main() -> None:
    uvicorn.run(
        "psx_data_hub.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.env == "local",
    )


if __name__ == "__main__":
    main()
