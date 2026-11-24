"""`python -m app.openapi > openapi.json`. The web app generates its TypeScript types from this file."""

import json

from app.main import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), indent=2, sort_keys=True))
