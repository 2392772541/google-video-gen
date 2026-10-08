"""Keep every test out of the live queue, including helpers with bound defaults."""
from pathlib import Path
import os
import socket
import subprocess
import threading

import pytest
from video_farm import db


@pytest.fixture(autouse=True)
def isolated_task_database(tmp_path, monkeypatch):
    production_path = db.DEFAULT_DB_PATH.resolve()
    connect = db.get_db_connection
    database = tmp_path / "tasks.db"
    db.init_db(database)

    def isolated_connect(db_path=production_path):
        # Many helpers bind DEFAULT_DB_PATH at definition time. Changing the
        # constant alone cannot protect those callers (or the web scheduler).
        target = Path(db_path) if db_path is not None else production_path
        if target.resolve() == production_path:
            target = database
        return connect(target)

    monkeypatch.setattr(db, "get_db_connection", isolated_connect)
    from video_farm.scheduler import VideoScheduler

    def forbid_live_scheduler(*args, **kwargs):
        raise AssertionError("Tests must not start the live generation scheduler")

    monkeypatch.setattr(VideoScheduler, "run_loop", forbid_live_scheduler)
    from video_farm import web
    monkeypatch.setattr(type(web.mgr), "initialize", forbid_live_scheduler)
    return database


@pytest.fixture(autouse=True)
def forbid_external_side_effects(request, monkeypatch):
    """Unit/integration tests may use ASGI TestClient, never the live service.

    Explicit mocks override these guards inside each test. Real browser/process/
    HTTP tests live in a separate opt-in file and are not part of the unit suite.
    """
    if (request.node.path.name == "test_live_e2e_sanity.py"
            and os.environ.get("VIDEO_FARM_LIVE_E2E") == "1"):
        return

    def forbidden(*args, **kwargs):
        raise AssertionError("External process/browser/network side effect in isolated test; mock it explicitly")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    # Windows asyncio creates its wakeup pipe with an internal loopback pair.
    # Allow only connect calls made synchronously inside socketpair, never
    # arbitrary localhost/live-service HTTP from the tests.
    pair_state = threading.local()
    original_pair = socket.socketpair
    original_connect = socket.socket.connect

    def internal_pair(*args, **kwargs):
        pair_state.active = True
        try:
            return original_pair(*args, **kwargs)
        finally:
            pair_state.active = False

    def guarded_connect(sock, address):
        if getattr(pair_state, "active", False):
            return original_connect(sock, address)
        return forbidden(sock, address)

    monkeypatch.setattr(socket, "socketpair", internal_pair)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    import playwright.sync_api
    import playwright.async_api
    monkeypatch.setattr(playwright.sync_api, "sync_playwright", forbidden)
    monkeypatch.setattr(playwright.async_api, "async_playwright", forbidden)
