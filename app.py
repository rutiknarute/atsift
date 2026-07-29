"""Entry point: serve the scanner API."""

from __future__ import annotations

from scanner.config import PORT
from scanner.web import create_app

app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT, threaded=True)
