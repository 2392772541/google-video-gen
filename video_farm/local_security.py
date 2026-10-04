"""Loopback-only browser boundary; local CLI clients remain supported (not authentication)."""
from urllib.parse import urlsplit
from pathlib import Path
import mimetypes
from fastapi import HTTPException

MEDIA_EXTENSIONS = {'.png','.jpg','.jpeg','.webp','.bmp','.gif','.mp4','.mov','.mkv','.webm','.mp3','.wav','.m4a','.aac','.ogg','.flac'}

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
        if protected:
            for name in ('origin', 'referer'):
                if name not in headers:
                    continue
                try:
                    origin = urlsplit(headers[name])
                    port = origin.port or (443 if origin.scheme == 'https' else 80)
                    valid = (origin.scheme, origin.hostname, port) == (target.scheme, target.hostname, target_port) and origin.username is None
                except ValueError:
                    valid = False
                if not valid:
                    return await reject(403, 'Cross-origin local service access denied')
            if headers.get('sec-fetch-site') == 'cross-site':
                return await reject(403, 'Cross-site local service access denied')
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
                message['headers'] = list(message.get('headers', [])) + [(b'x-content-type-options',b'nosniff'),(b'cross-origin-resource-policy',b'same-origin')]
            await send(message)
        try:
            await self.app(scope, limited_receive, safe_send)
        except Exception:
            if not oversized:
                raise
        if oversized and not started:
            await reject(413, 'Request exceeds body limit')
