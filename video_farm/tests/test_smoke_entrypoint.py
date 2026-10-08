"""The default verification entrypoint must never submit a cloud job."""
from pathlib import Path
import runpy
import urllib.request

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'run_e2e_verification.py'


def load_script(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Importing a smoke helper must not contact the live server')
    monkeypatch.setattr(urllib.request, 'urlopen', forbidden)
    return runpy.run_path(str(SCRIPT), run_name='smoke_import')


def test_verification_import_has_no_side_effects(monkeypatch):
    namespace = load_script(monkeypatch)
    assert callable(namespace.get('verify_service'))
    assert callable(namespace.get('main'))


def test_default_smoke_is_read_only_and_not_generation_evidence(monkeypatch):
    namespace = load_script(monkeypatch)
    requests = []

    def fetch(url, *, timeout):
        requests.append((url, timeout))
        if url.endswith('/api/overview'):
            return 200, {}, '{"tasks": {"total": 0}, "profiles": {"total": 0}, "scheduler_running": true}'
        if url.endswith('/api/vids/overview'):
            return 200, {}, '{"total_workflows": 0, "total_shots": 0}'
        return 200, {'Cache-Control': 'no-cache, no-store'}, 'content'

    report = namespace['verify_service'](fetch=fetch)
    assert report['read_only'] is True
    assert report['generation_verified'] is False
    assert report['checked_paths'] == [
        '/', '/vids', '/static/app.js', '/static/vids.js',
        '/api/overview', '/api/vids/overview',
    ]
    assert len(requests) == 6
    assert all(url.startswith('http://127.0.0.1:8088/') for url, _ in requests)


def test_smoke_fails_on_broken_service_instead_of_skipping(monkeypatch, capsys):
    namespace = load_script(monkeypatch)
    assert namespace['main']([]) == 1
    output = capsys.readouterr()
    assert '失败' in output.err
    assert '100% SUCCESS' not in output.out


def test_smoke_rejects_stale_static_cache(monkeypatch):
    namespace = load_script(monkeypatch)
    with pytest.raises(AssertionError, match='no-cache'):
        namespace['verify_service'](fetch=lambda url, timeout: (200, {}, '{}'))