"""
The Flask app and its routes.

Thin by design: parse the request, call into the scanner, shape the response.
"""

from __future__ import annotations

from functools import wraps

from flask import Flask, jsonify, request

from scanner import status
from scanner.boolean_search import ALL_CATEGORIES, ROLE_CATEGORY_LABELS
from scanner.companies import dataset_summary
from scanner.config import (
    DEFAULT_LOOKBACK_HOURS,
    LOOKBACK_OPTIONS,
    MAX_LOOKBACK_HOURS,
    OLLAMA_MODEL,
    SCANNER_API_TOKEN,
    USE_OLLAMA_ANALYSIS,
)
from scanner.scan import clamp_lookback, start_scan_thread
from scanner.store import load_jobs, load_viewed, mark_viewed


def require_token(view):
    """Bearer auth, active only when a token is configured."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not SCANNER_API_TOKEN:
            return view(*args, **kwargs)

        header = request.headers.get("Authorization", "")
        supplied = header[7:].strip() if header.startswith("Bearer ") else ""

        if supplied != SCANNER_API_TOKEN:
            return jsonify({"error": "unauthorized"}), 401

        return view(*args, **kwargs)

    return wrapper


def create_app() -> Flask:
    app = Flask(__name__)

    status.load_persisted()

    @app.after_request
    def cors(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization"
        )
        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, OPTIONS"
        )

        return response

    @app.route("/api/<path:_any>", methods=["OPTIONS"])
    def preflight(_any):
        return ("", 204)

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "scanning": status.is_running(),
                "analysis_enabled": USE_OLLAMA_ANALYSIS,
                "model": OLLAMA_MODEL,
            }
        )

    @app.get("/api/meta")
    @require_token
    def meta():
        return jsonify(
            {
                "categories": [
                    {"id": c, "label": ROLE_CATEGORY_LABELS[c]}
                    for c in ALL_CATEGORIES
                ],
                "datasets": dataset_summary(),
                "lookback_options": LOOKBACK_OPTIONS,
                "default_lookback_hours": DEFAULT_LOOKBACK_HOURS,
                "max_lookback_hours": MAX_LOOKBACK_HOURS,
            }
        )

    @app.get("/api/status")
    @require_token
    def scan_status():
        return jsonify(status.snapshot())

    @app.get("/api/jobs")
    @require_token
    def jobs():
        stored = load_jobs()
        viewed = load_viewed()
        records = stored.get("jobs") or []

        # An explicit narrower window filters the stored results without
        # forcing a re-scan.
        requested = request.args.get("lookback_hours")

        if requested is not None:
            hours = clamp_lookback(requested)
            records = [
                job
                for job in records
                if job.get("age_hours") is not None
                and job["age_hours"] <= hours
            ]

        category = request.args.get("category")

        if category:
            records = [
                job for job in records if category in (job.get("categories") or [])
            ]

        for job in records:
            job["viewed"] = job.get("uid") in viewed

        return jsonify(
            {
                "jobs": records,
                "count": len(records),
                "scanned_at": stored.get("scanned_at"),
                "lookback_hours": stored.get("lookback_hours"),
                "dataset": stored.get("dataset"),
            }
        )

    @app.post("/api/scan")
    @require_token
    def scan():
        payload = request.get_json(silent=True) or {}

        started = start_scan_thread(
            lookback_hours=payload.get(
                "lookback_hours", DEFAULT_LOOKBACK_HOURS
            ),
            dataset=payload.get("dataset", "main"),
            categories=payload.get("categories"),
        )

        if not started:
            return jsonify({"error": "a scan is already running"}), 409

        return jsonify({"started": True, "status": status.snapshot()})

    @app.post("/api/scan/stop")
    @require_token
    def stop_scan():
        status.request_cancel()

        return jsonify({"stopping": True})

    @app.post("/api/jobs/viewed")
    @require_token
    def viewed():
        payload = request.get_json(silent=True) or {}
        uid = str(payload.get("uid") or "").strip()

        if not uid:
            return jsonify({"error": "uid is required"}), 400

        return jsonify({"ok": True, "count": mark_viewed(uid)})

    return app
