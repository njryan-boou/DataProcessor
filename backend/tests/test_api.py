"""Exercise the public HTTP workflow and safe failures with isolated storage."""

import asyncio
import io
from types import SimpleNamespace
from uuid import UUID, uuid4

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from pandas.testing import assert_frame_equal

import app.api.datasets as dataset_api
import app.main as main_module
import app.utils.middleware as middleware_module
from app.config import Settings


CSV = b"age,salary,name,team\n20,40000,Ada,Eng\n40,80000,Bob,Ops\n,60000,,Eng\n40,80000,Bob,Ops\n"


@pytest.fixture
def settings():
    return Settings(
        _env_file=None, ai_api_key="", max_upload_mb=1, max_rows=10_000,
        max_columns=200, max_datasets=5, history_limit=20,
        max_memory_mb=16, dataset_ttl_seconds=60,
    )


@pytest.fixture
def client(monkeypatch, settings):
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(dataset_api, "get_settings", lambda: settings)
    monkeypatch.setattr(middleware_module, "get_settings", lambda: settings)
    with TestClient(main_module.create_app(), raise_server_exceptions=False) as value:
        yield value


def upload(client, data=CSV, filename="people.csv"):
    return client.post("/api/datasets/upload", files={"file": (filename, data, "text/csv")})


def dataset(client):
    response = upload(client)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["message"]
    assert "Traceback" not in response.text
    assert "site-packages" not in response.text
    assert "ValueError" not in response.text


def operation(client, identity, name, parameters):
    return client.post(f"/api/datasets/{identity}/transform", json={
        "operation": name, "parameters": parameters,
    })


def test_upload_metadata_preview_and_statistics(client):
    response = upload(client, filename="../reports/people.csv")
    assert response.status_code == 201
    info = response.json()
    UUID(info["id"])
    assert info["filename"] == "people.csv"
    assert info["file_size"] == len(CSV)
    assert (info["rows"], info["column_count"], info["missing_values"], info["duplicate_rows"]) == (4, 4, 2, 1)
    assert [column["type"] for column in info["columns"]] == ["numeric", "numeric", "text", "text"]
    assert info["version"] == 0
    assert [entry["operation"] for entry in info["history"]] == ["upload"]
    base = f"/api/datasets/{info['id']}"
    assert client.get(base).json() == info
    preview = client.get(f"{base}/preview", params={"page": 2, "page_size": 2})
    assert preview.status_code == 200
    assert preview.json()["total"] == 4
    assert preview.json()["rows"][0]["age"] is None
    assert len(preview.json()["rows"]) == 2
    assert client.get(f"{base}/preview", params={"page": 99}).json()["rows"] == []
    statistics = client.get(f"{base}/statistics")
    assert statistics.status_code == 200
    summaries = {item["name"]: item for item in statistics.json()["columns"]}
    assert summaries["age"]["count"] == 3
    assert summaries["age"]["mean"] == pytest.approx(100 / 3)
    assert summaries["age"]["missing"] == 1
    assert summaries["age"]["median"] == 40
    assert summaries["team"]["unique"] == 2
    assert {item["value"]: item["count"] for item in summaries["team"]["top_values"]} == {"Eng": 2, "Ops": 2}
    assert "duplicate_rows" in {warning["code"] for warning in statistics.json()["warnings"]}


def test_transform_history_undo_and_export_preserve_original(client):
    identity = dataset(client)
    saved_original = client.app.state.store.datasets[identity].original.copy(deep=True)
    removed = operation(client, identity, "remove_duplicates", {})
    assert removed.status_code == 200
    assert removed.json()["rows"] == 3
    filled = operation(client, identity, "fill_missing", {"column": "age", "method": "median"})
    assert filled.status_code == 200
    assert [step["operation"] for step in filled.json()["history"]] == ["upload", "remove_duplicates", "fill_missing"]
    assert client.get(f"/api/datasets/{identity}/preview").json()["rows"][2]["age"] == 30
    exported = client.get(f"/api/datasets/{identity}/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "people_processed.csv" in exported.headers["content-disposition"]
    parsed = pd.read_csv(io.StringIO(exported.text))
    assert len(parsed) == 3
    assert parsed["age"].tolist() == [20, 40, 30]
    assert_frame_equal(client.app.state.store.datasets[identity].original, saved_original)
    undone = client.post(f"/api/datasets/{identity}/undo")
    assert undone.status_code == 200
    assert undone.json()["version"] == 3
    assert client.get(f"/api/datasets/{identity}/preview").json()["rows"][2]["age"] is None
    assert client.post(f"/api/datasets/{identity}/undo").json()["rows"] == 4
    error(client.post(f"/api/datasets/{identity}/undo"), 409, "nothing_to_undo")
    assert_frame_equal(client.app.state.store.frame(identity), saved_original)


def test_batch_failure_is_atomic_and_success_records_each_step(client):
    identity = dataset(client)
    base = f"/api/datasets/{identity}"
    before = client.get(base).json()
    failed = client.post(f"{base}/transform-batch", json={"operations": [
        {"operation": "remove_duplicates", "parameters": {}},
        {"operation": "rename_column", "parameters": {"column": "missing", "new_name": "new"}},
    ]})
    error(failed, 400, "invalid_transformation")
    assert client.get(base).json() == before
    assert len(client.app.state.store.datasets[identity].states) == 1
    succeeded = client.post(f"{base}/transform-batch", json={"operations": [
        {"operation": "remove_duplicates", "parameters": {}},
        {"operation": "filter", "parameters": {"column": "salary", "operator": ">", "value": 50000}},
    ]})
    assert succeeded.status_code == 200
    assert succeeded.json()["rows"] == 2
    assert len(succeeded.json()["history"]) == 3
    assert client.post(f"{base}/undo").json()["rows"] == 3
    assert client.post(f"{base}/undo").json()["rows"] == 4


def test_empty_result_metadata_statistics_preview_and_header_only_export(client):
    identity = dataset(client)
    result = operation(client, identity, "filter", {"column": "age", "operator": ">", "value": 1000})
    assert result.status_code == 200
    assert result.json()["rows"] == 0
    assert result.json()["missing_values"] == 0
    base = f"/api/datasets/{identity}"
    assert client.get(f"{base}/preview").json()["rows"] == []
    statistics = client.get(f"{base}/statistics")
    assert statistics.status_code == 200
    assert all(column["count"] == 0 for column in statistics.json()["columns"])
    assert client.get(f"{base}/export").text == "age,salary,name,team\n"
    error(client.get(f"{base}/chart", params={"kind": "histogram", "x": "age"}), 400, "invalid_chart")
    assert client.post(f"{base}/undo").json()["rows"] == 4


def test_datetime_preview_statistics_line_chart_and_export(client):
    response = upload(client, b"date,value\n2025-01-01,10\n2025-02-01,20\n,30\n")
    identity = response.json()["id"]
    converted = operation(client, identity, "convert_type", {"column": "date", "type": "datetime"})
    assert converted.status_code == 200
    assert converted.json()["columns"][0]["type"] == "datetime"
    base = f"/api/datasets/{identity}"
    preview = client.get(f"{base}/preview")
    assert preview.status_code == 200
    assert preview.json()["rows"][0]["date"].startswith("2025-01-01T00:00:00")
    assert preview.json()["rows"][2]["date"] is None
    assert client.get(f"{base}/statistics").status_code == 200
    chart = client.get(f"{base}/chart", params={"kind": "line", "x": "date", "y": "value"})
    assert chart.status_code == 200
    assert len(chart.json()["points"]) == 2
    assert chart.json()["omitted_rows"] == 1
    assert "2025-01-01" in client.get(f"{base}/export").text


@pytest.mark.parametrize("filename,data,status,code", [
    ("people.xlsx", CSV, 415, "unsupported_file"),
    ("people.json", b"{}", 415, "unsupported_file"),
    ("people.csv", b"", 400, "empty_dataset"),
    ("people.csv", b"a,b\n", 400, "empty_dataset"),
    ("people.csv", b"a,a\n1,2\n", 400, "invalid_csv"),
    ("people.csv", b"a,b\n1,2,3\n", 400, "invalid_csv"),
    ("people.csv", b'a,b\n"unfinished,2\n', 400, "invalid_csv"),
    ("people.csv", b"a,b\n1,\x00\n", 400, "invalid_csv"),
    ("people.csv", b"a\n\xff\n", 400, "invalid_csv"),
    ("people.csv", b"a\ninf\n", 400, "invalid_csv"),
])
def test_bad_uploads_return_safe_errors_without_storing_dataset(client, filename, data, status, code):
    error(upload(client, data, filename), status, code)
    assert client.app.state.store.datasets == {}


def test_upload_size_limits_file_and_request_body(client):
    error(upload(client, b"a\n" + b"x" * (1024 * 1024)), 413, "oversized_upload")
    rejected = client.post("/api/datasets/upload", content=b"", headers={"content-length": str(3 * 1024 * 1024)})
    error(rejected, 413, "oversized_upload")
    malformed = client.post("/api/datasets/upload", content=b"", headers={"content-length": "invalid"})
    error(malformed, 400, "invalid_request")
    error(client.post("/api/datasets/anything/transform", content=b"x" * (1024 * 1024 + 1)), 413, "oversized_request")


def run_chunked_request(monkeypatch, settings, path, chunks, headers=()):
    """Exercise actual ASGI fragments because TestClient coalesces generators."""
    monkeypatch.setattr(middleware_module, "get_settings", lambda: settings)
    sent = []
    read_count = 0
    forwarded = bytearray()
    pieces = iter(enumerate(chunks))

    async def receive():
        nonlocal read_count
        index, chunk = next(pieces)
        read_count += 1
        return {"type": "http.request", "body": chunk, "more_body": index + 1 < len(chunks)}

    async def send(message):
        sent.append(message)

    async def downstream(scope, receive_body, send_response):
        while True:
            message = await receive_body()
            forwarded.extend(message["body"])
            if not message.get("more_body", False):
                break
        await send_response({"type": "http.response.start", "status": 200, "headers": []})
        await send_response({"type": "http.response.body", "body": b"{}"})

    asyncio.run(middleware_module.RequestSizeLimitMiddleware(downstream)(
        {"type": "http", "method": "POST", "path": path, "headers": list(headers)}, receive, send,
    ))
    return sent, bytes(forwarded), read_count


def test_chunked_and_dishonestly_declared_uploads_are_bounded_before_downstream(monkeypatch, settings):
    chunks = [b"x" * (1024 * 1024), b"y" * (1024 * 1024), b"z"]
    for headers in ((), ((b"content-length", b"1"),)):
        messages, forwarded, count = run_chunked_request(monkeypatch, settings, "/api/datasets/upload", chunks, headers)
        assert messages[0]["status"] == 413
        assert b"oversized_upload" in messages[1]["body"]
        assert forwarded == b""
        assert count == 3


def test_chunked_json_is_bounded_and_normal_fragmented_body_is_preserved(monkeypatch, settings):
    messages, forwarded, _ = run_chunked_request(monkeypatch, settings, "/api/datasets/id/transform", [b"x" * (1024 * 1024), b"x"])
    assert messages[0]["status"] == 413
    assert b"oversized_request" in messages[1]["body"]
    assert forwarded == b""
    messages, forwarded, _ = run_chunked_request(monkeypatch, settings, "/api/datasets/upload", [b"alpha", b"", b"beta"])
    assert messages[0]["status"] == 200
    assert forwarded == b"alphabeta"


def test_declared_oversized_request_is_rejected_before_body_reads(monkeypatch, settings):
    messages, forwarded, count = run_chunked_request(
        monkeypatch, settings, "/api/datasets/upload", [b"unused"], ((b"content-length", b"999999999"),),
    )
    assert messages[0]["status"] == 413
    assert forwarded == b""
    assert count == 0


@pytest.mark.parametrize("path", [
    "not-a-uuid", "not-a-uuid/preview", "not-a-uuid/statistics", "not-a-uuid/export",
])
def test_invalid_dataset_ids_are_safe(client, path):
    error(client.get(f"/api/datasets/{path}"), 422, "invalid_request")


def test_unknown_dataset_and_delete(client):
    error(client.get(f"/api/datasets/{uuid4()}"), 404, "dataset_not_found")
    identity = dataset(client)
    assert client.delete(f"/api/datasets/{identity}").status_code == 204
    error(client.get(f"/api/datasets/{identity}"), 404, "dataset_not_found")


@pytest.mark.parametrize("payload,status,code", [
    ({"operation": "execute_python", "parameters": {"code": "print('no')"}}, 422, "invalid_request"),
    ({"operation": "remove_duplicates", "parameters": {}, "extra": "no"}, 422, "invalid_request"),
    ({"operation": "remove_duplicates", "parameters": "bad"}, 422, "invalid_request"),
    ({"operation": "remove_duplicates", "parameters": {"extra": True}}, 400, "invalid_transformation"),
    ({"operation": "sort", "parameters": {"column": "unknown"}}, 400, "invalid_transformation"),
    ({"operation": "sort", "parameters": {"column": "age", "ascending": "false"}}, 400, "invalid_transformation"),
    ({"operation": "convert_type", "parameters": {"column": "name", "type": "numeric"}}, 400, "invalid_transformation"),
    ({"operation": "delete_columns", "parameters": {"columns": ["age", "salary", "name", "team"]}}, 400, "invalid_transformation"),
])
def test_invalid_transformation_requests_preserve_dataset(client, payload, status, code):
    identity = dataset(client)
    before = client.get(f"/api/datasets/{identity}").json()
    error(client.post(f"/api/datasets/{identity}/transform", json=payload), status, code)
    assert client.get(f"/api/datasets/{identity}").json() == before


def test_api_query_and_batch_validation(client):
    identity = dataset(client)
    base = f"/api/datasets/{identity}"
    for query in ({"page": 0}, {"page_size": 101}, {"page_size": 0}):
        error(client.get(f"{base}/preview", params=query), 422, "invalid_request")
    error(client.post(f"{base}/transform-batch", json={"operations": []}), 422, "invalid_request")
    error(client.post(f"{base}/transform-batch", json={"operations": [
        {"operation": "remove_duplicates", "parameters": {}} for _ in range(21)
    ]}), 422, "invalid_request")
    error(client.get(f"{base}/chart", params={"kind": "pie", "x": "age"}), 422, "invalid_request")
    error(client.get(f"{base}/chart", params={"kind": "histogram", "x": "age", "bins": 101}), 422, "invalid_request")
    error(client.post("/api/datasets/upload"), 422, "invalid_request")


@pytest.mark.parametrize("query", [
    {"kind": "histogram", "x": "age"},
    {"kind": "bar", "x": "team"},
    {"kind": "bar", "x": "team", "y": "salary"},
    {"kind": "line", "x": "age", "y": "salary"},
    {"kind": "scatter", "x": "age", "y": "salary"},
    {"kind": "box", "x": "salary"},
])
def test_all_chart_types_have_bounded_valid_data(client, query):
    identity = dataset(client)
    response = client.get(f"/api/datasets/{identity}/chart", params=query)
    assert response.status_code == 200, response.text
    assert response.json()["kind"] == query["kind"]
    assert response.json()["points"]
    assert len(response.json()["points"]) <= 2000


@pytest.mark.parametrize("query", [
    {"kind": "histogram", "x": "name"},
    {"kind": "histogram", "x": "age", "y": "salary"},
    {"kind": "scatter", "x": "team", "y": "salary"},
    {"kind": "scatter", "x": "age", "y": "name"},
    {"kind": "line", "x": "name", "y": "salary"},
    {"kind": "box", "x": "unknown"},
])
def test_invalid_chart_combinations_are_rejected(client, query):
    identity = dataset(client)
    error(client.get(f"/api/datasets/{identity}/chart", params=query), 400, "invalid_chart")


def test_health_security_headers_and_unexpected_error_redaction(client, monkeypatch):
    response = client.get("/api/health")
    assert response.json() == {"status": "ok", "name": "DataFlow"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"
    config = client.get("/api/config")
    assert config.status_code == 200
    assert config.json() == {"max_upload_mb": 1, "max_rows": 10_000, "max_columns": 200, "history_limit": 20}
    identity = dataset(client)

    def crash(_identity):
        raise RuntimeError("private backend implementation detail")

    monkeypatch.setattr(client.app.state.store, "metadata", crash)
    response = client.get(f"/api/datasets/{identity}")
    error(response, 500, "internal_error")
    assert "private backend implementation detail" not in response.text


def test_storage_capacity_history_limit_and_expiry_are_visible_via_api(client, monkeypatch):
    import app.services.storage as storage_module
    client.app.state.store.settings.max_datasets = 1
    identity = dataset(client)
    error(upload(client), 413, "storage_limit")
    client.app.state.store.settings.history_limit = 1
    assert operation(client, identity, "remove_duplicates", {}).status_code == 200
    error(operation(client, identity, "remove_duplicates", {}), 409, "history_limit")
    assert len(client.get(f"/api/datasets/{identity}").json()["history"]) == 2
    assert client.post(f"/api/datasets/{identity}/undo").status_code == 200
    assert operation(client, identity, "remove_duplicates", {}).status_code == 200
    touched = client.app.state.store.datasets[identity].touched
    monkeypatch.setattr(storage_module, "time", SimpleNamespace(monotonic=lambda: touched + 61))
    error(client.get(f"/api/datasets/{identity}"), 404, "dataset_not_found")
    assert upload(client).status_code == 201
