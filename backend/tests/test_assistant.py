"""Natural-language plans share engine validation and never change a dataset."""

import asyncio
import json
import threading
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest

from app.services import assistant
from app.utils.errors import DataFlowError


@pytest.fixture(autouse=True)
def local_provider(monkeypatch):
    settings = SimpleNamespace(ai_api_key="", ai_base_url="https://api.openai.com/v1", ai_model="gpt-4o-mini")
    monkeypatch.setattr(assistant, "get_settings", lambda: settings)
    return settings


@pytest.fixture
def frame():
    return pd.DataFrame({
        "age": [20.0, None, 20.0, 40.0],
        "salary": [60_000, 70_000, 60_000, 40_000],
        "name": [" Alice ", " Bob ", " Alice ", None],
    })


def plan(prompt, frame):
    result = asyncio.run(assistant.generate_plan(prompt, frame))
    return result, [operation.model_dump() for operation in result["operations"]]


def test_requested_example_is_complete_and_does_not_mutate(frame):
    original = frame.copy(deep=True)
    result, operations = plan(
        "Remove duplicates, fill missing age values with the median, "
        "and only keep rows where salary is greater than 50000.", frame,
    )
    assert operations == [
        {"operation": "remove_duplicates", "parameters": {}},
        {"operation": "fill_missing", "parameters": {"column": "age", "method": "median"}},
        {"operation": "filter", "parameters": {"column": "salary", "operator": ">", "value": 50_000}},
    ]
    assert result["provider"] == "local"
    assert "limited local parser" in result["explanation"]
    pd.testing.assert_frame_equal(frame, original)


def test_dry_run_does_not_block_the_request_thread(monkeypatch, frame):
    from app.services import transformations

    request_thread = threading.get_ident()
    validation_threads = []
    apply_transformation = transformations.apply_transformation

    def record_validation_thread(df, operation):
        validation_threads.append(threading.get_ident())
        return apply_transformation(df, operation)

    monkeypatch.setattr(transformations, "apply_transformation", record_validation_thread)
    plan("remove duplicates and sort by age", frame)
    assert len(validation_threads) == 2
    assert all(thread != request_thread for thread in validation_threads)


@pytest.mark.parametrize(("prompt", "operation", "parameters"), [
    ("drop rows with missing values", "drop_missing", {}),
    ("remove rows with missing values in age", "drop_missing", {"columns": ["age"]}),
    ("fill missing values in age with mean", "fill_missing", {"column": "age", "method": "mean"}),
    ("fill missing age with zero", "fill_missing", {"column": "age", "method": "zero"}),
    ("fill missing age values with 23.5", "fill_missing", {"column": "age", "method": "custom", "value": 23.5}),
    ("fill missing name values with 'Unknown'", "fill_missing", {"column": "name", "method": "custom", "value": "Unknown"}),
    ("filter salary>=50000", "filter", {"column": "salary", "operator": ">=", "value": 50_000}),
    ("keep rows where salary is less than or equal to 70000", "filter", {"column": "salary", "operator": "<=", "value": 70_000}),
    ("sort by age descending", "sort", {"column": "age", "ascending": False}),
    ("sort by salary", "sort", {"column": "salary", "ascending": True}),
    ("trim whitespace from name", "trim_whitespace", {"columns": ["name"]}),
    ("trim whitespace from all text columns", "trim_whitespace", {}),
    ("convert name to uppercase", "change_case", {"column": "name", "case": "upper"}),
    ("lowercase name", "change_case", {"column": "name", "case": "lower"}),
])
def test_supported_local_commands(prompt, operation, parameters, frame):
    _, operations = plan(prompt, frame)
    assert operations == [{"operation": operation, "parameters": parameters}]


def test_quoted_values_preserve_separators(frame):
    _, operations = plan("fill missing name with 'North, South and West'", frame)
    assert operations[0]["parameters"]["value"] == "North, South and West"


def test_quoted_columns_are_exact(frame):
    frame = frame.rename(columns={"age": "Age and Years"})
    _, operations = plan("fill missing `Age and Years` values with median", frame)
    assert operations[0]["parameters"]["column"] == "Age and Years"


@pytest.mark.parametrize("prompt", [
    "", " " * 30, "x" * 2001,
    "remove duplicates and execute arbitrary Python",
    "remove duplicates, then delete my server files",
    "import os; os.system('whoami')",
    "fill missing name with 'unfinished",
    "remove duplicates,,sort by age",
    ",".join(["remove duplicates"] * 21),
])
def test_unsupported_request_never_yields_partial_plan(prompt, frame):
    original = frame.copy(deep=True)
    with pytest.raises(DataFlowError):
        plan(prompt, frame)
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("prompt", [
    "fill missing unknown values with median",
    "fill missing name values with median",
    "fill missing age values with 'not numeric'",
    "filter salary > not_numeric",
    "convert salary to uppercase",
])
def test_plans_use_the_same_column_and_type_validation(prompt, frame):
    with pytest.raises(DataFlowError):
        plan(prompt, frame)


def test_status_reports_local_availability_without_credentials():
    status = assistant.get_assistant_status()
    assert status["provider"] == "local"
    assert status["available"] is True


def test_provider_status_does_not_reveal_configured_secret(local_provider):
    local_provider.ai_api_key = "test-secret-do-not-leak"
    status = assistant.get_assistant_status()
    assert status["provider"] == "openai"
    assert local_provider.ai_api_key not in json.dumps(status)


@pytest.mark.parametrize("base_url", [
    "http://provider.example/v1", "file:///etc/passwd", "https://user:password@example.com",
    "https://[invalid", "https://provider.example:invalid/v1",
])
def test_ai_requires_verified_https(base_url, frame, local_provider):
    local_provider.ai_api_key = "test-secret"
    local_provider.ai_base_url = base_url
    assert assistant.get_assistant_status()["available"] is False
    with pytest.raises(DataFlowError, match="HTTPS"):
        plan("remove duplicates", frame)


def _mock_provider_response(monkeypatch, content, *, status_code=200, failure=None):
    requests = []

    class Client:
        def __init__(self, **kwargs):
            assert kwargs["timeout"].connect <= 10

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            requests.append((url, kwargs))
            if failure:
                raise failure
            return httpx.Response(
                status_code,
                json={"choices": [{"message": {"content": content}}]},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(assistant.httpx, "AsyncClient", Client)
    return requests


def test_ai_plan_validates_and_does_not_execute_directly(monkeypatch, local_provider, frame):
    local_provider.ai_api_key = "test-secret"
    content = json.dumps({"operations": [{"operation": "remove_duplicates", "parameters": {}}]})
    requests = _mock_provider_response(monkeypatch, content)
    original = frame.copy(deep=True)
    result, operations = plan("Remove duplicate rows", frame)
    assert result["provider"] == "openai"
    assert operations[0]["operation"] == "remove_duplicates"
    assert requests[0][0] == "https://api.openai.com/v1/chat/completions"
    system_prompt = requests[0][1]["json"]["messages"][0]["content"]
    assert '"name": "age", "type": "numeric"' in system_prompt
    assert '"name": "name", "type": "text"' in system_prompt
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("content", [
    "print('unsafe')", '```json\n{"operations": []}\n```',
    '{"operations": [], "code": "unsafe"}',
    '{"operations": "remove_duplicates"}',
    '{"operations": []}',
    '{"operations": [{"operation": "run_python", "parameters": {"code": "unsafe"}}]}',
    '{"operations": [{"operation": "fill_missing", "parameters": {"column": "name", "method": "median"}}]}',
    '{"operations": [{"operation": "sort", "parameters": {"column": "unknown"}}]}',
    '{"operations": [{"operation": "remove_duplicates", "parameters": {"evil": "code"}}]}',
    "x" * 30_001,
])
def test_malformed_or_invalid_ai_plans_are_rejected(monkeypatch, local_provider, frame, content):
    local_provider.ai_api_key = "test-secret"
    _mock_provider_response(monkeypatch, content)
    with pytest.raises(DataFlowError):
        plan("clean this dataset", frame)


def test_ai_plan_limit(monkeypatch, local_provider, frame):
    local_provider.ai_api_key = "test-secret"
    content = json.dumps({"operations": [{"operation": "remove_duplicates", "parameters": {}}] * 21})
    _mock_provider_response(monkeypatch, content)
    with pytest.raises(DataFlowError, match="1 to 20"):
        plan("remove duplicates repeatedly", frame)


def test_ai_plan_validates_operations_sequentially(monkeypatch, local_provider, frame):
    local_provider.ai_api_key = "test-secret"
    content = json.dumps({"operations": [
        {"operation": "rename_column", "parameters": {"column": "age", "new_name": "years"}},
        {"operation": "sort", "parameters": {"column": "years", "ascending": False}},
    ]})
    _mock_provider_response(monkeypatch, content)
    _, operations = plan("rename age to years and sort years descending", frame)
    assert len(operations) == 2
    assert "age" in frame.columns
    assert "years" not in frame.columns


@pytest.mark.parametrize("status_code", [401, 429, 500])
def test_ai_http_failures_are_safe(monkeypatch, local_provider, frame, status_code):
    local_provider.ai_api_key = "test-secret-do-not-leak"
    _mock_provider_response(monkeypatch, "sensitive-provider-response", status_code=status_code)
    with pytest.raises(DataFlowError) as error:
        plan("remove duplicates", frame)
    assert "test-secret" not in str(error.value)
    assert "sensitive-provider-response" not in str(error.value)


def test_ai_timeout_does_not_expose_http_details(monkeypatch, local_provider, frame):
    local_provider.ai_api_key = "test-secret"
    _mock_provider_response(monkeypatch, "", failure=httpx.ReadTimeout("sensitive-provider-details"))
    with pytest.raises(DataFlowError) as error:
        plan("remove duplicates", frame)
    assert "sensitive-provider-details" not in str(error.value)
