"""EngineWatch's local web app and bounded, in-memory prediction API."""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
from pathlib import Path
import re
import sys
from functools import lru_cache

from flask import Flask, Response, jsonify, request, send_from_directory
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR / "src"))
COLUMNS = ["engine_id", "cycle"] + [f"setting_{i}" for i in range(1, 4)] + [f"sensor_{i}" for i in range(1, 22)]
MAX_ROWS = 5000


def parse_sensor_text(text: str) -> list[dict]:
    """Accept a named CSV or NASA's 26-column whitespace text for one engine."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Choose a non-empty CSV or NASA sensor text file.")
    if len(text.encode("utf-8")) > 1_900_000:
        raise ValueError("The sensor file must be smaller than 1.9 MB.")
    lines = [line.strip() for line in text.lstrip("\ufeff").splitlines() if line.strip()]
    if len(lines) > MAX_ROWS + 1:
        raise ValueError(f"Upload at most {MAX_ROWS:,} readings for one engine.")
    if "," in lines[0]:
        records = list(csv.reader(lines))
    else:
        records = [re.split(r"\s+", line) for line in lines]
    first = [cell.strip() for cell in records[0]]
    try:
        [float(cell) for cell in first]
        header = COLUMNS
    except ValueError:
        aliases = {"unit": "engine_id", "unit_number": "engine_id", "engine": "engine_id", "time": "cycle"}
        aliases.update({f"settings_{i}": f"setting_{i}" for i in range(1, 4)})
        header = [aliases.get(cell.lower(), cell.lower()) for cell in first]
        if len(header) != len(COLUMNS) or set(header) != set(COLUMNS):
            raise ValueError("Use the 26 columns in the downloadable sample: engine_id, cycle, setting_1–3, sensor_1–21.")
        records = records[1:]
    if not records or len(records) > MAX_ROWS:
        raise ValueError(f"Upload between 1 and {MAX_ROWS:,} readings.")
    rows = []
    for index, values in enumerate(records, start=1):
        if len(values) != len(COLUMNS):
            raise ValueError(f"Reading {index} has {len(values)} columns; exactly 26 are required.")
        try:
            row = {key: float(value.strip()) for key, value in zip(header, values)}
        except ValueError as exc:
            raise ValueError(f"Reading {index} contains a missing or non-numeric value.") from exc
        if not all(math.isfinite(value) for value in row.values()):
            raise ValueError(f"Reading {index} contains an infinite or missing value.")
        for key in ("engine_id", "cycle"):
            if row[key] <= 0 or row[key] > 2_147_483_647 or not row[key].is_integer():
                raise ValueError(f"Reading {index}: {key} must be a positive whole number no greater than 2,147,483,647.")
            row[key] = int(row[key])
        if any(abs(row[key]) > 1e12 for key in COLUMNS[2:]):
            raise ValueError(f"Reading {index} has a measurement outside the supported numeric range (absolute value at most 1e12). Check the sensor units.")
        rows.append(row)
    if len({row["engine_id"] for row in rows}) != 1:
        raise ValueError("Upload one engine at a time. Split a fleet file by engine_id first.")
    cycles = [row["cycle"] for row in rows]
    if any(right <= left for left, right in zip(cycles, cycles[1:])):
        raise ValueError("Cycles must be unique and in increasing order. Sort the file chronologically.")
    return rows


def create_app(project_dir: Path | None = None) -> Flask:
    root = Path(project_dir or PROJECT_DIR).resolve()
    app = Flask(__name__, static_folder=str(root / "static"))
    app.config.update(MAX_CONTENT_LENGTH=2_000_000, JSON_SORT_KEYS=False)

    @lru_cache(maxsize=1)
    def demo():
        return json.loads((root / "artifacts" / "demo.json").read_text(encoding="utf-8"))

    @lru_cache(maxsize=1)
    def predictor():
        from enginewatch.inference import EngineWatchPredictor
        return EngineWatchPredictor.from_artifacts(root)

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        return response

    @app.get("/")
    def index():
        return send_from_directory(root / "static", "index.html")

    @app.get("/health")
    def health():
        ready = (root / "artifacts" / "demo.json").exists() and (root / "models" / "model.joblib").exists()
        return jsonify({"status": "ready" if ready else "missing_artifacts", "project": "EngineWatch"}), 200 if ready else 503

    @app.get("/api/summary")
    def summary():
        data = demo()
        return jsonify({key: data[key] for key in ("summary", "fleet", "feature_importance")})

    @app.get("/api/engines/<int:engine_id>")
    def engine(engine_id):
        history = demo()["engines"].get(str(engine_id))
        if history is None:
            return jsonify(error="That benchmark engine does not exist. Choose an engine from 1 to 100."), 404
        return jsonify(history)

    @app.get("/api/sample")
    def sample():
        return send_from_directory(root / "data" / "examples", "sample.csv", as_attachment=True, download_name="enginewatch-sample.csv")

    @app.post("/api/predict")
    def predict():
        if not request.is_json:
            return jsonify(error="Send a JSON object containing the sensor file as text."), 415
        payload = request.get_json()
        if not isinstance(payload, dict):
            return jsonify(error="Send a JSON object containing the sensor file as text."), 400
        try:
            rows = parse_sensor_text(payload.get("text"))
            from threadpoolctl import threadpool_limits
            with threadpool_limits(limits=2):
                result = predictor().predict_history(rows)
            if result.get("true_rul") is None:
                result.pop("true_rul", None)
        except (ValueError, KeyError, TypeError, OverflowError) as exc:
            return jsonify(error=str(exc)), 400
        return jsonify(result)

    @app.get("/api/engines/<int:engine_id>/download")
    def download_predictions(engine_id):
        history = demo()["engines"].get(str(engine_id))
        if history is None:
            return jsonify(error="Engine not found."), 404
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["engine_id", "cycle", "predicted_rul", "lower_rul", "upper_rul", "benchmark_true_rul"])
        for i, cycle in enumerate(history["cycles"]):
            writer.writerow([engine_id, cycle, history["predictions"][i], history["lower"][i], history["upper"][i], history["true_rul"][i]])
        return Response(buffer.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="engine-{engine_id}-predictions.csv"'})

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_):
        return jsonify(error="The upload is too large. Choose a sensor file smaller than 1.9 MB."), 413

    @app.errorhandler(BadRequest)
    def bad_request(_):
        return jsonify(error="The request contains invalid JSON."), 400

    @app.errorhandler(FileNotFoundError)
    def missing_artifacts(_):
        return jsonify(error="Model artifacts are missing. Run python -m enginewatch.train from the project folder."), 503

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the EngineWatch demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5050)
    args = parser.parse_args()
    print(f"EngineWatch: http://{args.host}:{args.port}")
    create_app().run(host=args.host, port=args.port, debug=False)
