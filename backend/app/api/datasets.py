from pathlib import Path
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.models.schemas import (
    AssistantPlan, AssistantRequest, ChartResponse, DatasetMetadata, DatasetPreview,
    DatasetStatistics, Transformation, TransformationBatch,
)
from app.services.parsing import parse_upload
from app.services.storage import InMemoryDatasetStore
from app.utils.errors import DataFlowError

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def store(request: Request) -> InMemoryDatasetStore:
    return request.app.state.store


@router.post('/upload', response_model=DatasetMetadata, status_code=201)
async def upload(request: Request, file: UploadFile = File(...)) -> DatasetMetadata:
    settings = get_settings()
    limit = settings.max_upload_mb * 1024 * 1024
    data = bytearray()
    try:
        while chunk := await file.read(64 * 1024):
            if len(data) + len(chunk) > limit:
                raise DataFlowError(f"The upload limit is {settings.max_upload_mb} MB.", 413, "oversized_upload")
            data.extend(chunk)
        filename, frame = await run_in_threadpool(parse_upload, file.filename or 'dataset.csv', bytes(data), settings)
        return await run_in_threadpool(store(request).create, filename, bytes(data), frame)
    finally:
        await file.close()


@router.post('/demo', response_model=DatasetMetadata, status_code=201)
def demo(request: Request) -> DatasetMetadata:
    data = (Path(__file__).resolve().parents[2] / 'sample.csv').read_bytes()
    filename, frame = parse_upload('team_insights.csv', data, get_settings())
    return store(request).create(filename, data, frame)


@router.get('/{dataset_id}', response_model=DatasetMetadata)
def metadata(dataset_id: UUID, request: Request) -> DatasetMetadata:
    return store(request).metadata(str(dataset_id))


@router.get('/{dataset_id}/preview', response_model=DatasetPreview)
def preview(dataset_id: UUID, request: Request, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100)) -> DatasetPreview:
    return store(request).preview(str(dataset_id), page, page_size)


@router.get('/{dataset_id}/statistics', response_model=DatasetStatistics)
def statistics(dataset_id: UUID, request: Request) -> dict:
    from app.services.statistics import compute_statistics
    return compute_statistics(store(request).frame(str(dataset_id)))


@router.post('/{dataset_id}/transform', response_model=DatasetMetadata)
def transform(dataset_id: UUID, payload: Transformation, request: Request) -> DatasetMetadata:
    return store(request).transform(str(dataset_id), [payload])


@router.post('/{dataset_id}/transform-batch', response_model=DatasetMetadata)
def transform_batch(dataset_id: UUID, payload: TransformationBatch, request: Request) -> DatasetMetadata:
    return store(request).transform(str(dataset_id), payload.operations)


@router.post('/{dataset_id}/undo', response_model=DatasetMetadata)
def undo(dataset_id: UUID, request: Request) -> DatasetMetadata:
    return store(request).undo(str(dataset_id))


@router.get('/{dataset_id}/chart', response_model=ChartResponse)
def chart(dataset_id: UUID, request: Request, kind: Literal['histogram', 'bar', 'line', 'scatter', 'box'], x: str = Query(min_length=1), y: str | None = None, bins: int = Query(default=20, ge=1, le=100)) -> dict:
    from app.services.charts import chart_data
    return chart_data(store(request).frame(str(dataset_id)), kind, x, y, bins)


@router.get('/{dataset_id}/export')
def export(dataset_id: UUID, request: Request) -> StreamingResponse:
    info = store(request).metadata(str(dataset_id))
    frame = store(request).frame(str(dataset_id))
    def generate():
        if len(frame) == 0:
            yield frame.to_csv(index=False).encode('utf-8')
        for start in range(0, len(frame), 1000):
            yield frame.iloc[start:start + 1000].to_csv(index=False, header=start == 0).encode('utf-8')
    filename = Path(info.filename).stem + '_processed.csv'
    return StreamingResponse(generate(), media_type='text/csv; charset=utf-8', headers={
        'Content-Disposition': f"attachment; filename*=UTF-8''{quote(filename)}",
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    })


@router.post('/{dataset_id}/assistant/plan', response_model=AssistantPlan)
async def assistant_plan(dataset_id: UUID, payload: AssistantRequest, request: Request) -> dict:
    from app.services.assistant import generate_plan
    frame = await run_in_threadpool(store(request).frame, str(dataset_id))
    return await generate_plan(payload.prompt, frame)


@router.delete('/{dataset_id}', status_code=204)
def delete(dataset_id: UUID, request: Request) -> None:
    store(request).delete(str(dataset_id))
