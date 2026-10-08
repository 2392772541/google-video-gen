"""Account probes/login cannot race generation or accept agreements."""
import threading
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from video_farm import db, web, onboard
from video_farm.models import Profile

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(web.mgr, 'scheduler', SimpleNamespace(lock=threading.Lock(), active_tasks={}))
    monkeypatch.setattr(web, 'check_chrome_running_for_profile', Mock(return_value=False))
    monkeypatch.setattr(web, 'watch_chrome_login_exit', Mock())
    if hasattr(web, '_PROFILE_ACTIONS'):
        web._PROFILE_ACTIONS.clear()
    yield TestClient(web.app, base_url='http://127.0.0.1:8088')
    if hasattr(web, '_PROFILE_ACTIONS'):
        web._PROFILE_ACTIONS.clear()

@pytest.mark.parametrize('endpoint', ['verify-auth','auto-onboard','launch-login','launch-gemini-login'])
def test_busy_account_cannot_be_probed_or_reopened(client, monkeypatch, endpoint):
    db.add_profile(Profile(id='p-owned', name='owned', status='busy'))
    board = Mock(return_value={'success':True})
    launch = Mock()
    monkeypatch.setattr(web, 'auto_onboard_profile', board)
    monkeypatch.setattr(web.subprocess, 'Popen', launch)
    response=client.post('/api/profiles/p-owned/'+endpoint)
    assert response.status_code == 409, response.text
    board.assert_not_called()
    launch.assert_not_called()
    assert db.get_profile_by_id('p-owned').status == 'busy'


def test_probe_reserves_account_outside_slow_browser_and_preserves_cooldown(client, monkeypatch):
    cooldown='2099-01-01T00:00:00+08:00'
    db.add_profile(Profile(id='p-probe', name='probe', status='cooldown', cooldown_until=cooldown))
    def inspect(name, **kwargs):
        assert db.get_profile_by_id('p-probe').status == 'busy'
        assert not web.mgr.scheduler.lock.locked(), 'slow browser blocks queue operations'
        assert client.post('/api/profiles/p-probe/reset-status').status_code == 409
        return {'success':True, 'flow_ok':True, 'gemini_ok':False}
    monkeypatch.setattr(web,'auto_onboard_profile',inspect)
    response=client.post('/api/profiles/p-probe/auto-onboard')
    assert response.status_code == 200, response.text
    saved=db.get_profile_by_id('p-probe')
    assert (saved.status,saved.cooldown_until)==('cooldown',cooldown)


def test_failed_probe_releases_only_its_reservation(client, monkeypatch):
    db.add_profile(Profile(id='p-probe',name='probe'))
    monkeypatch.setattr(web,'auto_onboard_profile',Mock(side_effect=RuntimeError('probe failed')))
    with pytest.raises(RuntimeError,match='probe failed'):
        web.api_auto_onboard('p-probe')
    assert db.get_profile_by_id('p-probe').status=='idle'
    assert not web._PROFILE_ACTIONS


def test_login_completion_does_not_reset_new_owner_or_auth(client):
    db.add_profile(Profile(id='p-login', name='login', status='auth_expired'))
    original, token=web._reserve_profile_action('p-login', 'login')
    web._release_profile_action('p-login', token)
    assert db.get_profile_by_id('p-login').status=='auth_expired'
    newer, new_token=web._reserve_profile_action('p-login', 'verify')
    web._release_profile_action('p-login', token, auth_valid=True)
    assert web._PROFILE_ACTIONS['p-login']['token']==new_token
    assert db.get_profile_by_id('p-login').status=='busy'
    web._release_profile_action('p-login', new_token)


def test_agreement_requires_user_action_without_click(tmp_path, monkeypatch):
    agree=Mock()
    agree.is_visible.return_value=True
    agree.evaluate.return_value=False
    page=Mock()
    page.url='https://flow.google.com/'
    page.query_selector.return_value=None
    page.query_selector_all.side_effect=lambda selector: [agree] if 'I agree' in selector else []
    page.wait_for_selector.side_effect=RuntimeError('no editor')
    browser=Mock()
    browser.pages=[page]
    browser.new_page.return_value=page
    pw=SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=Mock(return_value=browser)))
    context=Mock()
    context.__enter__=Mock(return_value=pw)
    context.__exit__=Mock(return_value=False)
    import playwright.sync_api
    monkeypatch.setattr(playwright.sync_api,'sync_playwright',lambda:context)
    monkeypatch.setattr(web,'check_chrome_running_for_profile',lambda p:False)
    monkeypatch.setattr(web,'profile_directory',lambda p:tmp_path/'chrome')
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    result=onboard.auto_onboard_profile('agreement',create_default_project=False)
    agree.click.assert_not_called()
    assert result.get('error_code')=='USER_ACTION_REQUIRED',result
    assert not result.get('flow_ok')
    browser.close.assert_called()
