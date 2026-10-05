"""Temporary storage boundaries, expiry, and snapshot ownership."""

from types import SimpleNamespace

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from app.config import Settings
from app.models.schemas import Transformation
import app.services.storage as storage_module
from app.services.storage import InMemoryDatasetStore
from app.utils.errors import DataFlowError


@pytest.fixture
def store():
    return InMemoryDatasetStore(Settings(
        _env_file=None, ai_api_key="", max_datasets=2, max_memory_mb=16,
        dataset_ttl_seconds=60, history_limit=2,
    ))


def create(store, frame=None):
    if frame is None:
        frame = pd.DataFrame({"number": [2, 1, 1]})
    return store.create("data.csv", b"number\n2\n1\n1\n", frame).id


def op(name, **parameters):
    return Transformation(operation=name, parameters=parameters)


def test_create_and_frame_returned_data_do_not_alias_original(store):
    source = pd.DataFrame({"number": [2, 1, 1]})
    expected = source.copy(deep=True)
    identity = create(store, source)
    source.loc[0, "number"] = 99
    returned = store.frame(identity)
    returned.loc[1, "number"] = 88
    assert_frame_equal(store.frame(identity), expected)
    store.transform(identity, [op("sort", column="number")])
    assert_frame_equal(store.datasets[identity].original, expected)
    store.undo(identity)
    assert_frame_equal(store.frame(identity), expected)


def test_dataset_capacity_frees_after_delete(store):
    first = create(store)
    create(store)
    with pytest.raises(DataFlowError, match="Too many active datasets"):
        create(store)
    assert len(store.datasets) == 2
    store.delete(first)
    create(store)
    assert len(store.datasets) == 2


def test_create_rejects_frame_exceeding_memory_capacity(store):
    with pytest.raises(DataFlowError, match="Temporary storage is full"):
        create(store, pd.DataFrame({"text": ["x" * (17 * 1024 * 1024)]}))
    assert store.datasets == {}


def test_history_snapshots_count_toward_memory_and_failed_step_is_atomic(store):
    source = pd.DataFrame({"text": ["x" * (6 * 1024 * 1024)]})
    identity = create(store, source)
    store.transform(identity, [op("sort", column="text")])
    before = store.metadata(identity)
    with pytest.raises(DataFlowError, match="Temporary storage is full"):
        store.transform(identity, [op("sort", column="text")])
    assert store.metadata(identity) == before
    assert len(store.datasets[identity].states) == 2
    store.undo(identity)
    assert store.transform(identity, [op("sort", column="text")]).rows == 1


def test_batch_pending_states_count_toward_memory_and_do_not_partially_commit(store):
    identity = create(store, pd.DataFrame({"text": ["x" * (6 * 1024 * 1024)]}))
    before = store.metadata(identity)
    with pytest.raises(DataFlowError, match="Temporary storage is full"):
        store.transform(identity, [op("sort", column="text"), op("sort", column="text")])
    assert store.metadata(identity) == before
    assert len(store.datasets[identity].states) == 1


def test_expiry_is_idle_based_refreshes_on_access_and_frees_capacity(store, monkeypatch):
    identity = create(store)
    started = store.datasets[identity].touched
    clock = [started + 59]
    monkeypatch.setattr(storage_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    assert store.metadata(identity).rows == 3
    clock[0] = started + 100
    assert store.frame(identity).shape == (3, 1)
    clock[0] = started + 161
    with pytest.raises(DataFlowError, match="not found or expired"):
        store.metadata(identity)
    assert identity not in store.datasets
    assert create(store)


def test_history_limit_rejects_entire_batch_before_any_changes(store):
    identity = create(store)
    before = store.metadata(identity)
    with pytest.raises(DataFlowError, match="Undo history is limited"):
        store.transform(identity, [op("sort", column="number") for _ in range(3)])
    assert store.metadata(identity) == before
    store.transform(identity, [op("sort", column="number"), op("remove_duplicates")])
    assert len(store.metadata(identity).history) == 3
    with pytest.raises(DataFlowError, match="Undo history is limited"):
        store.transform(identity, [op("sort", column="number")])
    store.undo(identity)
    assert store.transform(identity, [op("sort", column="number")]).rows == 3


def test_failed_batch_retains_previous_versions_history_and_rows(store):
    identity = create(store)
    before = store.metadata(identity)
    original = store.frame(identity)
    with pytest.raises(DataFlowError, match="Unknown column"):
        store.transform(identity, [op("remove_duplicates"), op("sort", column="unknown")])
    assert store.metadata(identity) == before
    assert_frame_equal(store.frame(identity), original)


def test_row_and_column_limits_check_generated_snapshots_atomically(store):
    identity = create(store)
    before = store.metadata(identity)
    store.settings.max_columns = 1
    with pytest.raises(DataFlowError, match="result exceeds dataset limits"):
        store.transform(identity, [op("detect_outliers", column="number")])
    assert store.metadata(identity) == before
