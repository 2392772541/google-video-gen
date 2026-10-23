"""Loopback-only browser boundary; local CLI clients remain supported (not authentication)."""
from urllib.parse import urlsplit
from pathlib import Path
import mimetypes
from fastapi import HTTPException

MEDIA_EXTENSIONS = {'.png','.jpg','.jpeg','.webp','.bmp','.gif','.mp4','.mov','.mkv','.webm','.mp3','.wav','.m4a','.aac','.ogg','.flac'}
ALLOWED_LOOPBACK_PORTS = {3000, 8088, 8089, 8317, 23210, 5173, 5174, 8080}

def local_file(value: str, *, downloads=False, managed_root=None) -> Path:
    # Do not double URL-decode: FastAPI already decoded the query string.
    value = value.strip().strip('\"\'')
    if value.lower().startswith('file:'):
        raise HTTPException(400, '请使用本地绝对文件路径，而不是 file URL')
    if value.startswith(('\\\\', '//')) or '://' in value:
        raise HTTPException(403, '不允许网络路径或远程文件')
    p = Path(value).resolve()
    if str(p).startswith(('\\\\', '//')):
        raise HTTPException(403, '不允许网络路径')
    allowed = p.suffix.lower() in MEDIA_EXTENSIONS
    if downloads and managed_root and p.is_relative_to(Path(managed_root).resolve()):
        allowed = allowed or p.suffix.lower() in {'.zip','.json','.txt','.srt','.vtt'}
    if not allowed:
        raise HTTPException(403, '仅允许访问媒体文件或受管理的导出文件')
    if not p.is_file():
        raise HTTPException(404, '文件不存在')
    return p

def media_type(p: Path) -> str:
    return mimetypes.guess_type(str(p))[0] or 'application/octet-stream'

class LocalBrowserBoundary:
    def __init__(self, app, max_body_bytes=512 * 1024 * 1024):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = {k.decode('latin1').lower(): v.decode('latin1') for k,v in scope.get('headers', [])}
        host = headers.get('host', '')
        try:
            target = urlsplit(scope.get('scheme', 'http') + '://' + host)
            valid_host = target.hostname in {'localhost', '127.0.0.1', '::1'} and target.username is None
            target_port = target.port or (443 if target.scheme == 'https' else 80)
        except ValueError:
            valid_host = False
        async def reject(code, text):
            body = ('{"detail":"' + text + '"}').encode()
            await send({'type':'http.response.start','status':code,'headers':[(b'content-type',b'application/json; charset=utf-8'),(b'x-content-type-options',b'nosniff')]})
            await send({'type':'http.response.body','body':body})
        if not valid_host:
            return await reject(403, 'Only loopback Host is allowed')
        protected = scope['path'].startswith(('/api/', '/media/'))
        origin_header = headers.get('origin')
        is_cross_origin_loopback = False
        if protected:
            for name in ('origin', 'referer'):
                if name not in headers:
                    continue
                try:
                    origin = urlsplit(headers[name])
                    port = origin.port or (443 if origin.scheme == 'https' else 80)
                    loopback_hosts = {'localhost', '127.0.0.1', '::1'}
                    is_loopback = (origin.hostname in loopback_hosts and target.hostname in loopback_hosts)
                    valid = (
                        origin.scheme in ('http', 'https')
                        and (origin.scheme == target.scheme)
                        and is_loopback
                        and (port == target_port or port in ALLOWED_LOOPBACK_PORTS)
                        and origin.username is None
                    )
                    if valid and is_loopback and port != target_port:
                        is_cross_origin_loopback = True
                except ValueError:
                    valid = False
                if not valid:
                    return await reject(403, 'Cross-origin local service access denied')
            if headers.get('sec-fetch-site') == 'cross-site':
                return await reject(403, 'Cross-site local service access denied')

            # Handle CORS preflight OPTIONS request for loopback callers
            if scope.get('method') == 'OPTIONS' and origin_header:
                cors_headers = [
                    (b'content-type', b'text/plain; charset=utf-8'),
                    (b'access-control-allow-origin', origin_header.encode('latin1')),
                    (b'access-control-allow-credentials', b'true'),
                    (b'access-control-allow-methods', b'GET, POST, PUT, DELETE, PATCH, OPTIONS'),
                    (b'access-control-allow-headers', b'Content-Type, Authorization, X-Requested-With, Range, Accept, Origin'),
                    (b'access-control-max-age', b'86400'),
                    (b'x-content-type-options', b'nosniff'),
                    (b'cross-origin-resource-policy', b'cross-origin'),
                ]
                await send({'type': 'http.response.start', 'status': 204, 'headers': cors_headers})
                await send({'type': 'http.response.body', 'body': b''})
                return
        try:
            if int(headers.get('content-length', '0')) > self.max_body_bytes:
                return await reject(413, 'Request exceeds 512 MiB limit')
        except ValueError:
            return await reject(400, 'Invalid Content-Length')
        size = 0
        oversized = False
        started = False
        async def limited_receive():
            nonlocal size, oversized
            message = await receive()
            if message['type'] == 'http.request':
                size += len(message.get('body', b''))
                if size > self.max_body_bytes:
                    oversized = True
                    raise ValueError('Request body limit exceeded')
            return message
        async def safe_send(message):
            nonlocal started
            if oversized:
                if message['type'] == 'http.response.start' and not started:
                    started = True
                    await reject(413, 'Request exceeds body limit')
                return
            if message['type'] == 'http.response.start':
                started = True
                extra_headers = [(b'x-content-type-options', b'nosniff')]
                is_media_path = scope['path'].startswith(('/media/', '/v1/videos/', '/api/vids/assets/'))
                if is_cross_origin_loopback or is_media_path:
                    extra_headers.append((b'cross-origin-resource-policy', b'cross-origin'))
                    if origin_header:
                        extra_headers.append((b'access-control-allow-origin', origin_header.encode('latin1')))
                        extra_headers.append((b'access-control-allow-credentials', b'true'))
                        extra_headers.append((b'access-control-allow-methods', b'GET, POST, PUT, DELETE, PATCH, OPTIONS, HEAD'))
                        extra_headers.append((b'access-control-allow-headers', b'*'))
                    else:
                        extra_headers.append((b'access-control-allow-origin', b'*'))
                else:
                    extra_headers.append((b'cross-origin-resource-policy', b'same-origin'))
                message['headers'] = list(message.get('headers', [])) + extra_headers
            await send(message)
        try:
            await self.app(scope, limited_receive, safe_send)
        except Exception:
            if not oversized:
                raise
        if oversized and not started:
            await reject(413, 'Request exceeds body limit')
