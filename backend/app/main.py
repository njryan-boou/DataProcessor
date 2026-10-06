"""Application wiring only; business logic lives in services."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.datasets import router
from app.config import get_settings
from app.services.frontend import configure_frontend
from app.services.storage import InMemoryDatasetStore
from app.utils.errors import DataFlowError
from app.utils.middleware import RequestSizeLimitMiddleware


def create_app() -> FastAPI:
    app = FastAPI(title='DataFlow API', version='0.1.0')
    app.state.store = InMemoryDatasetStore(get_settings())
    app.include_router(router)
    app.add_middleware(RequestSizeLimitMiddleware)

    @app.middleware('http')
    async def secure_responses(request: Request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(DataFlowError)
    async def public_error(request: Request, error: DataFlowError):
        return JSONResponse({'error': {'code': error.code, 'message': error.message}}, status_code=error.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        return JSONResponse({'error': {'code': 'invalid_request', 'message': 'Invalid request parameters. Check the operation, column names, and values.'}}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception):
        import logging
        logging.getLogger('dataflow').exception('Unexpected server error')
        return JSONResponse({'error': {'code': 'internal_error', 'message': 'The server could not complete this request.'}}, status_code=500)

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'name': 'DataFlow'}

    @app.get('/api/config')
    def capabilities():
        settings = get_settings()
        return {'max_upload_mb': settings.max_upload_mb, 'max_rows': settings.max_rows, 'max_columns': settings.max_columns, 'history_limit': settings.history_limit}

    @app.get('/api/assistant/status')
    def assistant_status():
        from app.services.assistant import get_assistant_status
        return get_assistant_status()

    configure_frontend(app, get_settings().frontend_dist)
    return app


app = create_app()
