import os
import re
import sys
import time
import sqlite3
from pathlib import Path
from typing import Dict, Any, Optional

def auto_onboard_profile(profile_name: str, create_default_project: bool = True) -> Dict[str, Any]:
    """
    针对新添加的 Google 账号 Profile，全自动完成一次性服务条款/协议同意、弹窗消除与默认项目初始化。
    支持 Google Flow 与 Gemini 网页版双端。
    """
    appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    gflow_base = Path(appdata) / "ffroliva" / "gflow-cli"
    profile_dir = gflow_base / f"profile_{profile_name}"
    profile_dir.mkdir(parents=True, exist_ok=True)
    
    # 确保写入 chrome marker
    marker = profile_dir / ".gflow_browser_strategy"
    marker.write_text("chrome", encoding="utf-8")

    # 检查是否有独占 Chrome 正在运行
    from .web import check_chrome_running_for_profile
    if check_chrome_running_for_profile(profile_name):
        return {
            "success": False,
            "error_code": "PROFILE_LOCKED",
            "message": f"账号 [{profile_name}] 的 Chrome 窗口正在桌面上打开！请先在桌面上点一下【同意/继续】并关闭该 Chrome 窗口，或在控制台点击【⏹ 关占用 Chrome】后重试。"
        }

    from playwright.sync_api import sync_playwright
    
    flow_ok = False
    gemini_ok = False
    project_id = None
    actions_taken = []
    
    try:
        with sync_playwright() as pw:
            launch_args = [
                                "--no-sandbox"
            ]
            browser = pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir.resolve()),
                channel="chrome",
                headless=True,
                args=launch_args
            )
            page = browser.pages[0] if browser.pages else browser.new_page()

            # ================= 1. Google Flow 自动化协议与项目就绪 =================
            try:
                page.goto("https://flow.google.com/", timeout=35000, wait_until="domcontentloaded")
                page.wait_for_timeout(3500)

                # 循环消除多步前置协议与弹窗 (最多 6 轮)
                button_selectors = [
                    "button:has-text('继续')", "button:has-text('下一步')", "button:has-text('开始')",
                    "button:has-text('同意')", "button:has-text('我了解')", "button:has-text('我同意')",
                    "button:has-text('I agree')", "button:has-text('Continue')", "button:has-text('Next')",
                    "button:has-text('Get started')", "button:has-text('Accept')", "button:has-text('Agree')",
                    "button:has-text('Got it')", "button:has-text('知道了')", "button:has-text('完成')",
                    "button:has-text('Done')", "button:has-text('Start Creating')", "button:has-text('开始创作')"
                ]
                btn_match_str = ", ".join(button_selectors)

                for step in range(6):
                    # 尝试滚动条款容器以便激活'同意'按钮
                    page.evaluate("""() => {
                        const el = document.querySelector('.privacy-content') || 
                                   document.querySelector('.cdk-overlay-pane div[style*="overflow"]') ||
                                   document.querySelector('[role="dialog"] div[style*="overflow"]');
                        if (el) { el.scrollTop = el.scrollHeight; el.dispatchEvent(new Event('scroll')); }
                    }""")
                    
                    panes = page.query_selector_all(".cdk-overlay-pane, [role='dialog'], .mat-mdc-dialog-container, div.terms-dialog")
                    clicked = False
                    for pane in panes:
                        btn = pane.query_selector(btn_match_str)
                        if btn and btn.is_visible() and not btn.evaluate("el => el.disabled || el.getAttribute('disabled')"):
                            btn_text = btn.inner_text().strip()
                            btn.click()
                            actions_taken.append(f"Flow点击协议弹窗按钮: [{btn_text}]")
                            clicked = True
                            page.wait_for_timeout(2500)
                            break
                    if not clicked:
                        # 看看页面主体是否有全局的同意/开始按钮
                        global_btn = page.query_selector("button:has-text('Get started'), button:has-text('开始使用'), button:has-text('开始创作')")
                        if global_btn and global_btn.is_visible() and "project" not in page.url:
                            b_text = global_btn.inner_text().strip()
                            global_btn.click()
                            actions_taken.append(f"Flow点击首页进入按钮: [{b_text}]")
                            page.wait_for_timeout(3000)
                        else:
                            break

                # 关闭右侧会话栏与引导气泡
                close_btn = page.query_selector("button.header-action:has-text('close'), button[aria-label='关闭'], button[aria-label='Close']")
                if close_btn and close_btn.is_visible():
                    try:
                        close_btn.click()
                        actions_taken.append("关闭右侧会话侧边栏")
                        page.wait_for_timeout(1000)
                    except Exception:
                        pass

                got_it = page.query_selector("button:has-text('知道了'), button:has-text('Got it')")
                if got_it and got_it.is_visible():
                    try:
                        got_it.click()
                        actions_taken.append("关闭引导提示气泡")
                        page.wait_for_timeout(1000)
                    except Exception:
                        pass

                # 检查是否已进入登录后的 Flow 系统
                if "accounts.google.com" not in page.url and ("flow.google.com" in page.url or "project" in page.url):
                    flow_ok = True

                # 查找或创建默认 Project
                if create_default_project and flow_ok:
                    existing_card = page.query_selector('a[href*="/project/"]')
                    if existing_card:
                        href = existing_card.get_attribute("href")
                        m = re.search(r'/project/([a-zA-Z0-9_-]+)', href or "")
                        if m:
                            project_id = m.group(1)
                    if not project_id:
                        m = re.search(r'/project/([a-zA-Z0-9_-]+)', page.url)
                        if m:
                            project_id = m.group(1)
                    if not project_id:
                        # 尝试点击新建项目
                        create_btn = page.query_selector("button:has-text('新建项目'), button:has-text('New Project'), button:has-text('Start Creating'), a[href*='project']")
                        if create_btn and create_btn.is_visible():
                            create_btn.click()
                            actions_taken.append("点击新建默认项目")
                            page.wait_for_timeout(5000)
                            m = re.search(r'/project/([a-zA-Z0-9_-]+)', page.url)
                            if m:
                                project_id = m.group(1)

                if project_id:
                    import uuid
                    db_file = gflow_base / "gflow.db"
                    with sqlite3.connect(db_file) as conn:
                        conn.execute(
                            "INSERT OR REPLACE INTO projects (id, profile_name, flow_project_id, title, source, created_at) VALUES (?, ?, ?, ?, ?, datetime('now'))",
                            (str(uuid.uuid4()), profile_name, project_id, 'Default Project', 'auto_onboard')
                        )
                    actions_taken.append(f"绑定默认工程: [{project_id}]")
            except Exception as e:
                actions_taken.append(f"Flow处理警告: {e}")

            # ================= 2. Gemini 网页版自动化协议 =================
            try:
                page.goto("https://gemini.google.com/app", timeout=25000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)

                # 查找 Gemini 的协议或欢迎弹窗
                gemini_btns = page.query_selector_all("button:has-text('我同意'), button:has-text('同意'), button:has-text('接受'), button:has-text('I agree'), button:has-text('Accept'), button:has-text('Continue'), button:has-text('开始使用'), button:has-text('下一步')")
                for gb in gemini_btns:
                    if gb.is_visible() and not gb.evaluate("el => el.disabled"):
                        t_txt = gb.inner_text().strip()
                        gb.click()
                        actions_taken.append(f"Gemini点击同意弹窗: [{t_txt}]")
                        page.wait_for_timeout(2000)

                # 检查输入框是否就绪
                input_selector = 'div.ql-editor[contenteditable="true"], rich-textarea div[contenteditable="true"], textarea'
                try:
                    page.wait_for_selector(input_selector, timeout=5000)
                    gemini_ok = True
                except Exception:
                    gemini_ok = False
            except Exception as e:
                actions_taken.append(f"Gemini处理警告: {e}")

            browser.close()

    except Exception as exc:
        err_str = str(exc).lower()
        if any(k in err_str for k in ["target closed", "lock", "singleton", "already running", "in use", "exitcode=21"]):
            return {
                "success": False,
                "error_code": "PROFILE_LOCKED",
                "message": f"Chrome Profile 正在被独占打开，请先关闭桌面 Chrome 窗口或点击【⏹ 关占用 Chrome】后再试。"
            }
        return {
            "success": False,
            "error_code": "ONBOARD_ERROR",
            "message": f"自动化初始化发生异常: {exc}"
        }

    if flow_ok or gemini_ok:
        summary_parts = []
        if flow_ok:
            summary_parts.append("Google Flow ✅就绪")
        if gemini_ok:
            summary_parts.append("Gemini 网页版 ✅就绪")
        
        msg = f"🎉 账号 [{profile_name}] 自动协议确认与环境初始化成功！({', '.join(summary_parts)})"
        if actions_taken:
            msg += f" 执行动作: {'; '.join(actions_taken[:3])}"
        return {
            "success": True,
            "flow_ok": flow_ok,
            "gemini_ok": gemini_ok,
            "project_id": project_id,
            "actions": actions_taken,
            "message": msg
        }
    else:
        return {
            "success": False,
            "error_code": "STILL_UNAUTHENTICATED",
            "actions": actions_taken,
            "message": f"账号 [{profile_name}] 尚未检测到完整登录凭据。请先点击【🔑 登录 Flow】或【🌐 登录 Gemini】在弹出的 Chrome 窗口中完成账号登录并点一次【同意】，关闭窗口即可。"
        }


def get_profile_flow_project_id(profile_name: str) -> Optional[str]:
    """快速从 gflow.db 查询指定 profile 是否已绑定 flow_project_id"""
    try:
        appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        gflow_db = Path(appdata) / "ffroliva" / "gflow-cli" / "gflow.db"
        if gflow_db.exists():
            with sqlite3.connect(str(gflow_db)) as conn:
                row = conn.execute(
                    "SELECT flow_project_id FROM projects WHERE profile_name = ? ORDER BY rowid DESC LIMIT 1",
                    (profile_name,)
                ).fetchone()
                if row and row[0]:
                    return str(row[0]).strip()
    except Exception as e:
        print(f"[get_profile_flow_project_id] 查询 profile [{profile_name}] 工程异常: {e}")
    return None

def ensure_profile_onboarded(profile_name: str) -> Optional[str]:
    """
    全自动化前置防线：确保 profile 必定拥有 Flow 专属工程
    1. 先从本地数据库秒级查询；若已有 project_id，立即返回；
    2. 若未绑定，立即自动调用无头 auto_onboard_profile 进行协议确认并建立默认项目；
    3. 成功后返回 project_id，确保 CLI 调度绝对不会报 401 闪退。
    """
    pid = get_profile_flow_project_id(profile_name)
    if pid:
        return pid

    print(f"[ensure_profile_onboarded] Profile [{profile_name}] 尚未绑定工程，自动触发无头 Onboarding 自愈...")
    res = auto_onboard_profile(profile_name, create_default_project=True)
    if res.get("success") and res.get("project_id"):
        return res["project_id"]

    return get_profile_flow_project_id(profile_name)
