import csv
import io
import json
from pathlib import Path

import pytest

from app import COLUMNS, create_app, parse_sensor_text

ROOT = Path(__file__).resolve().parents[1]


def sensor_csv(cycles=(1, 2), engines=(1, 1), extra=None):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    for engine, cycle in zip(engines, cycles):
        values = [engine, cycle] + [0.0, 0.0, 100.0] + [float(i) for i in range(1, 22)]
        if extra is not None:
            values[extra[0]] = extra[1]
        writer.writerow(values)
    return buffer.getvalue()


def test_upload_accepts_csv_and_nasa_text():
    rows = parse_sensor_text(sensor_csv())
    nasa = "\n".join(" ".join(str(row[column]) for column in COLUMNS) for row in rows)
    assert parse_sensor_text(nasa) == rows


@pytest.mark.parametrize("text,match", [
    ("", "non-empty"),
    (sensor_csv(cycles=(2, 1)), "increasing"),
    (sensor_csv(cycles=(1, 1)), "unique"),
    (sensor_csv(engines=(1, 2)), "one engine"),
    (sensor_csv(extra=(5, "NaN")), "missing"),
    (sensor_csv(extra=(5, "inf")), "infinite"),
    (sensor_csv(extra=(1, 1.5)), "whole"),
    (sensor_csv(extra=(1, "1e100")), "whole"),
    (sensor_csv(extra=(5, "1e100")), "numeric range"),
    ("engine_id,cycle\n1,2", "26 columns"),
])
def test_invalid_uploads_are_rejected(text, match):
    with pytest.raises(ValueError, match=match):
        parse_sensor_text(text)


@pytest.fixture(scope="module")
def client():
    return create_app(ROOT).test_client()


def test_app_serves_real_fleet_and_unknown_engine(client):
    assert client.get("/").status_code == 200
    assert client.get("/health").json["status"] == "ready"
    response = client.get("/api/summary")
    assert response.status_code == 200
    assert len(response.json["fleet"]) == 100
    assert response.json["summary"]["test_engines"] == 100
    assert client.get("/api/engines/999").status_code == 404


def test_upload_prediction_matches_saved_benchmark(client):
    sample = client.get("/api/sample")
    assert sample.status_code == 200
    response = client.post("/api/predict", json={"text": sample.data.decode("utf-8")})
    assert response.status_code == 200, response.json
    prediction = response.json
    expected = client.get(f"/api/engines/{prediction['id']}").json
    assert prediction["cycles"] == expected["cycles"]
    assert prediction["predictions"] == pytest.approx(expected["predictions"], abs=0.02)
    assert "true_rul" not in prediction
    assert all(low <= point <= high for low, point, high in zip(prediction["lower"], prediction["predictions"], prediction["upper"]))


def test_prefix_predictions_do_not_change_when_future_arrives(client):
    sample = client.get("/api/sample").data.decode("utf-8")
    lines = sample.splitlines()
    prefix = "\n".join(lines[:16])
    early = client.post("/api/predict", json={"text": prefix}).json
    full = client.post("/api/predict", json={"text": sample}).json
    assert early["predictions"] == pytest.approx(full["predictions"][:15], abs=0.001)


def test_api_handles_invalid_and_oversized_input(client):
    assert client.post("/api/predict", json={"text": "oops"}).status_code == 400
    assert client.post("/api/predict", data="oops").status_code == 415
    assert client.post("/api/predict", json=[]).status_code == 400
    assert client.post("/api/predict", data="{", content_type="application/json").status_code == 400
    assert client.post("/api/predict", json={"text": "1" * 2_100_000}).status_code == 413
    response = client.post("/api/predict", json={"text": sensor_csv(extra=(1, "1e100"))})
    assert response.status_code == 400 and "error" in response.json


def test_download_reconciles_to_engine_history(client):
    response = client.get("/api/engines/1/download")
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.data.decode())))
    engine = client.get("/api/engines/1").json
    assert len(rows) == len(engine["cycles"])
    assert float(rows[-1]["predicted_rul"]) == engine["predictions"][-1]
