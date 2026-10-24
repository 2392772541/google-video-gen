import os
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Dict, Any, Optional


AGREEMENT_SELECTOR = ", ".join([
    "button:has-text('I agree')", "button:has-text('Accept')",
    "button:has-text('我同意')", "button:has-text('同意')", "button:has-text('接受')",
    "button:has-text('Get started')", "button:has-text('开始使用')",
])


def needs_user_action(page) -> bool:
    # Never click/scroll a legal agreement or infer consent from a URL.
    return any(button.is_visible() for button in page.query_selector_all(AGREEMENT_SELECTOR))


def auto_onboard_profile(profile_name: str, create_default_project: bool = True) -> Dict[str, Any]:
    """Inspect readiness; explicit initialization may create a project after consent.

    The calling API owns the account reservation. Workers never invoke this
    browser path automatically or transparently retry a submitted generation.
    """
    from .web import check_chrome_running_for_profile, profile_directory
    profile_dir = profile_directory(profile_name)
    if check_chrome_running_for_profile(profile_name):
        return {"success": False, "error_code": "PROFILE_LOCKED",
                "message": "此账号的 Chrome 已打开，请先关闭窗口再验证；不会强制释放生成任务。"}
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / '.gflow_browser_strategy').write_text('chrome', encoding='utf-8')
    flow_ok, gemini_ok, project_id = False, False, None
    actions, user_actions = [], []
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir), channel='chrome', headless=True,
                args=['--no-sandbox'])
            try:
                page = browser.pages[0] if browser.pages else browser.new_page()
                try:
                    page.goto('https://flow.google.com/', timeout=25000, wait_until='domcontentloaded')
                    controls = "a[href*='/project/'], button:has-text('New project'), button:has-text('新建项目'), [contenteditable='true'], textarea"
                    try:
                        page.wait_for_selector(controls + ', ' + AGREEMENT_SELECTOR, timeout=8000)
                    except Exception:
                        pass
                    if needs_user_action(page):
                        user_actions.append('Google Flow')
                    elif re.match(r'https://(?:flow\.google\.com/|labs\.google/fx/)', page.url):
                        control = page.query_selector(controls)
                        flow_ok = bool(control and control.is_visible())
                        if flow_ok and create_default_project:
                            card = page.query_selector("a[href*='/project/']")
                            href = card.get_attribute('href') if card else page.url
                            match = re.search(r'/project/([a-zA-Z0-9_-]+)', href or '')
                            project_id = match.group(1) if match else None
                            if not project_id:
                                button = page.query_selector("button:has-text('New project'), button:has-text('新建项目')")
                                if button and button.is_visible():
                                    button.click()
                                    actions.append('创建默认工程（未提交生成）')
                                    page.wait_for_url('**/project/**', timeout=15000)
                                    match = re.search(r'/project/([a-zA-Z0-9_-]+)', page.url)
                                    project_id = match.group(1) if match else None
                            if project_id:
                                appdata = os.environ.get('LOCALAPPDATA') or str(Path.home()/'AppData'/'Local')
                                database = Path(appdata)/'ffroliva'/'gflow-cli'/'gflow.db'
                                with sqlite3.connect(database) as conn:
                                    conn.execute(
                                        "INSERT OR REPLACE INTO projects (id, profile_name, flow_project_id, title, source, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
                                        (str(uuid.uuid4()), profile_name, project_id, 'Default Project', 'manual_initialization'))
                                actions.append('绑定默认工程')
                except Exception as exc:
                    actions.append(f'Flow探测失败: {exc}')
                try:
                    page.goto('https://gemini.google.com/app', timeout=20000, wait_until='domcontentloaded')
                    editor = 'div.ql-editor[contenteditable="true"], rich-textarea div[contenteditable="true"], textarea'
                    try:
                        page.wait_for_selector(editor + ', ' + AGREEMENT_SELECTOR, timeout=6000)
                    except Exception:
                        pass
                    if needs_user_action(page):
                        user_actions.append('Gemini')
                    elif page.url.startswith('https://gemini.google.com/app'):
                        control = page.query_selector(editor)
                        gemini_ok = bool(control and control.is_visible())
                except Exception as exc:
                    actions.append(f'Gemini探测失败: {exc}')
            finally:
                browser.close()
    except Exception as exc:
        locked = any(k in str(exc).lower() for k in ['singleton', 'already running', 'in use', 'exitcode=21'])
        return {'success': False, 'error_code': 'PROFILE_LOCKED' if locked else 'VERIFY_ERROR',
                'message': f'账号探测未完成: {exc}'}
    result = {'success': bool((flow_ok or gemini_ok) and not user_actions),
              'flow_ok': flow_ok, 'gemini_ok': gemini_ok, 'vids_ok': None,
              'project_id': project_id, 'actions': actions, 'user_action_engines': user_actions}
    if user_actions:
        result.update(error_code='USER_ACTION_REQUIRED', message=' / '.join(user_actions)+' 需要您在登录窗口亲自完成协议或初始化；系统未自动同意，也未提交生成。')
    elif flow_ok or gemini_ok:
        result['message'] = '账号探测完成：Flow '+('就绪' if flow_ok else '未确认')+'，Gemini '+('就绪' if gemini_ok else '未确认')+'；Google Vids 仍需单独验证。'
    else:
        result.update(error_code='AUTH_UNCONFIRMED', message='未确认有效登录或可用编辑器，请在登录窗口完成登录后重新验证。')
    return result


def get_profile_flow_project_id(profile_name: str) -> Optional[str]:
    """快速从 gflow.db 查询指定 profile 是否已绑定 flow_project_id，严格过滤确保为 36 位标准 UUID"""
    try:
        appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        gflow_db = Path(appdata) / "ffroliva" / "gflow-cli" / "gflow.db"
        if gflow_db.exists():
            with sqlite3.connect(str(gflow_db)) as conn:
                rows = conn.execute(
                    "SELECT flow_project_id FROM projects WHERE profile_name = ? ORDER BY rowid DESC",
                    (profile_name,)
                ).fetchall()
                for row in rows:
                    if row and row[0]:
                        pid = str(row[0]).strip()
                        if re.fullmatch(r"[0-9a-fA-F-]{36}", pid):
                            return pid
    except Exception as e:
        print(f"[get_profile_flow_project_id] 查询 profile [{profile_name}] 工程异常: {e}")
    return None

def ensure_profile_onboarded(profile_name: str) -> Optional[str]:
    """Read the existing binding only; never accept agreements or open a browser."""
    return get_profile_flow_project_id(profile_name)
