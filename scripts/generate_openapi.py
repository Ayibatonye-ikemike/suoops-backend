from __future__ import annotations

import json
from pathlib import Path

from fastapi.openapi.utils import get_openapi

from app.api.main import app


def main() -> None:
    spec = get_openapi(
        title=app.title,
        version="1.0.0",
        description="WhatsInvoice API",
        routes=app.routes,
    )
    target = Path(__file__).resolve().parents[1] / "frontend" / "openapi.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(spec, indent=2))
    print(f"OpenAPI spec written to {target}")


if __name__ == "__main__":
    main()
