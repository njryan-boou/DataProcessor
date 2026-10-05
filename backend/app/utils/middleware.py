"""Bound requests before multipart parsing, including chunked uploads."""
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http' or scope['method'] not in {'POST', 'PUT', 'PATCH'}:
            await self.app(scope, receive, send)
            return
        upload = scope['path'] == '/api/datasets/upload'
        limit = (get_settings().max_upload_mb + 1) * 1024 * 1024 if upload else 1024 * 1024
        headers = dict(scope.get('headers', []))
        length = headers.get(b'content-length')
        try:
            declared = int(length) if length is not None else 0
        except ValueError:
            response = JSONResponse({'error': {'code': 'invalid_request', 'message': 'Invalid request size.'}}, status_code=400)
            await response(scope, receive, send)
            return
        body = bytearray()
        replayed = False
        if declared <= limit and declared >= 0:
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                chunk = message.get('body', b'')
                if len(body) + len(chunk) > limit:
                    break
                body.extend(chunk)
                if not message.get('more_body', False):
                    async def replay():
                        nonlocal replayed
                        if not replayed:
                            replayed = True
                            return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                        return await receive()
                    await self.app(scope, replay, send)
                    return
        response = JSONResponse({'error': {
            'code': 'oversized_upload' if upload else 'oversized_request',
            'message': 'The file exceeds the upload limit.' if upload else 'The request is too large.',
        }}, status_code=413, headers={'X-Content-Type-Options': 'nosniff'})
        await response(scope, receive, send)
