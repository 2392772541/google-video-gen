from __future__ import annotations
import os
import sys
import time
import json
import base64
import urllib.request
import threading
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

from .models import Task, Profile
import psutil

_PROFILE_LOCKS = {}
_PROFILE_LOCKS_GUARD = threading.Lock()

def get_profile_lock(profile_name: str) -> threading.Lock:
    with _PROFILE_LOCKS_GUARD:
        if profile_name not in _PROFILE_LOCKS:
            _PROFILE_LOCKS[profile_name] = threading.Lock()
        return _PROFILE_LOCKS[profile_name]

def unlock_profile_processes(profile_dir: Path, profile_name: str) -> int:
    """彻底清理指定 Profile 残留的无头/崩溃 Chrome 进程与目录锁，杜绝 TargetClosedError (exitCode=21)"""
    target_substr = f"profile_{profile_name}".lower()
    killed = 0
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'chrome' in proc.info['name'].lower():
                cmd_str = " ".join(proc.info.get('cmdline') or []).lower()
                if target_substr in cmd_str:
                    proc.kill()
                    killed += 1
        except Exception:
            pass
    if killed > 0:
        time.sleep(0.5)
    for lock_name in ["lockfile", "SingletonLock", "SingletonSocket", "SingletonCookie"]:
        lf = profile_dir / lock_name
        if lf.exists():
            try:
                lf.unlink()
            except Exception:
                pass
    return killed

class GeminiWebWorker:
    """
    Worker for orchestrating video generation on gemini.google.com/videos via persistent Chrome profiles.
    - Zero cookie leakage: uses local isolated Chrome profile directories.
    - Automatic overlay / discovery-card dismissal to prevent pointer event interception.
    - Direct navigation to https://gemini.google.com/videos with native [Videos] mode capsule.
    - Native UI aspect ratio selection: Landscape (16:9) vs Portrait (9:16).
    - Native UI model selection: 3.8 Flash, 3.1 Pro, Extended thinking, etc.
    - Early refusal / text-script detection to prevent idle timeout loops.
    - Dual-track video extraction: authenticated in-page blob fetch & native download button capture.
    """
    def __init__(
        self,
        output_dir: Path = Path("video_farm_data/outputs"),
        timeout_sec: int = 360,
        headless: bool = True
    ):
        self.output_dir = output_dir.resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_sec = timeout_sec
        self.headless = headless
        self._active_sessions: Dict[str, Dict[str, Any]] = {}
        self._sessions_lock = threading.Lock()

    def cancel_task(self, task_id: str) -> bool:
        """强行终止指定任务的 Gemini 会话并清理 Chrome 进程"""
        with self._sessions_lock:
            sess = self._active_sessions.get(task_id)
            if sess:
                sess["cancelled"] = True
                browser = sess.get("browser")
                if browser:
                    try:
                        browser.close()
                    except Exception:
                        pass
                profile = sess.get("profile")
                if profile:
                    try:
                        profile_dir = self._resolve_profile_dir(profile)
                        unlock_profile_processes(profile_dir, profile.name)
                    except Exception:
                        pass
                return True
        return False

    def _resolve_profile_dir(self, profile: Profile) -> Path:
        if profile.profile_path and Path(profile.profile_path).exists():
            return Path(profile.profile_path).resolve()
        appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(appdata) / "ffroliva" / "gflow-cli" / f"profile_{profile.name}"

    def _dismiss_overlays(self, page, logs: list) -> None:
        """主动检测并关闭欢迎弹窗、条款提示、新功能推荐遮罩层，防止拦截输入与点击。"""
        dismiss_selectors = [
            "mat-dialog-container button[aria-label*='Close']",
            "mat-dialog-container button[aria-label*='close']",
            "[role='dialog'] button:has-text('Got it')",
            "[role='dialog'] button:has-text('Dismiss')",
            "[role='dialog'] button:has-text('Not now')",
            "[role='dialog'] button:has-text('Close')",
            "[role='dialog'] button:has-text('知道了')",
            "[role='dialog'] button:has-text('关闭')",
            "[role='dialog'] button:has-text('稍后再说')",
            "[role='dialog'] button:has-text('Accept all')",
            "[role='dialog'] button:has-text('I agree')",
            "[role='dialog'] button:has-text('同意')",
            ".cdk-overlay-container button[aria-label*='Close']",
            ".cdk-overlay-container button:has-text('Got it')",
            ".cdk-overlay-backdrop"
        ]
        for sel in dismiss_selectors:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    logs.append(f"检测到页面弹出浮层遮罩 ({sel})，自动点击关闭...")
                    btn.click(force=True)
                    page.wait_for_timeout(600)
            except Exception:
                pass
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass

    def execute_task(self, task: Task, profile: Profile) -> Dict[str, Any]:
        worker_name = threading.current_thread().name
        profile_dir = self._resolve_profile_dir(profile)
        
        logs = []
        logs.append(f"[{worker_name}] 启动 Gemini 网页版原生视频生成引擎 (Profile: {profile.name})")
        logs.append(f"Profile 目录: {profile_dir}")
        logs.append(f"Prompt: {task.prompt}")

        if not profile_dir.exists():
            profile_dir.mkdir(parents=True, exist_ok=True)
            logs.append(f"初始化建立 Profile 用户数据目录: {profile_dir}")

        from playwright.sync_api import sync_playwright

        output_video_path = self.output_dir / f"{task.id}.mp4"

        try:
            with sync_playwright() as p:
                launch_args = [
                                        "--no-sandbox"
                ]
                
                logs.append("正在拉起 Chrome 浏览器会话...")
                try:
                    browser = p.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir.resolve()),
                        channel="chrome",
                        headless=self.headless,
                        args=launch_args
                    )
                    with self._sessions_lock:
                        self._active_sessions[task.id] = {
                            "browser": browser,
                            "profile": profile,
                            "cancelled": False
                        }
                except Exception as launch_exc:
                    lexc_str = str(launch_exc).lower()
                    logs.append(f"拉起浏览器异常: {launch_exc}")
                    if any(k in lexc_str for k in ["target closed", "browser has been closed", "singleton", "lock", "in use", "already running"]):
                        logs.append("【检测到目录锁】Chrome Profile 正在被外部浏览器窗口独占占用。")
                        return {
                            "success": False,
                            "pid": os.getpid(),
                            "error_code": "PROFILE_LOCKED",
                            "error_message": f"Profile [{profile.name}] 正在被运行中的 Chrome 窗口占用。请在桌面关闭 Chrome 窗口或在控制台点击【⏹ 关闭占用 Chrome】后再试。",
                            "output_video_path": None,
                            "logs": "\n".join(logs)
                        }
                    raise launch_exc

                try:
                    page = browser.new_page()
                    
                    # 1. 优先直达原生视频生成工作台
                    logs.append("正在打开 Gemini 视频工作区 https://gemini.google.com/videos ...")
                    try:
                        page.goto("https://gemini.google.com/videos", timeout=35000)
                    except Exception as ge:
                        logs.append(f"直接打开 /videos 超时或异常，尝试主入口 /app ... ({ge})")
                        page.goto("https://gemini.google.com/app", timeout=35000)

                    page.wait_for_timeout(3000)
                    self._dismiss_overlays(page, logs)

                    cur_url = page.url
                    page_title = page.title()
                    logs.append(f"页面加载完成: Title='{page_title}', URL='{cur_url}'")

                    # 若被重定向到 /app，主动点击左侧导航栏的 Videos 进入视频模式
                    if "/videos" not in cur_url:
                        logs.append("当前未在 /videos 路径，正在尝试切换至左侧【Videos】专属工作区...")
                        video_nav_selectors = [
                            'a[href="/videos"]',
                            'a[href*="videos"]',
                            'gem-nav-list-item:has-text("Videos")',
                            'button:has-text("Videos")',
                            '[data-test-id*="video"]'
                        ]
                        for nav_sel in video_nav_selectors:
                            try:
                                vnav = page.query_selector(nav_sel)
                                if vnav and vnav.is_visible():
                                    vnav.click(force=True)
                                    page.wait_for_timeout(2000)
                                    self._dismiss_overlays(page, logs)
                                    logs.append(f"成功切换至视频工作区: URL='{page.url}'")
                                    break
                            except Exception:
                                pass

                    # 2. 登录状态核验：优先寻找输入框
                    input_selector = 'rich-textarea div[contenteditable="true"], div.ql-editor[contenteditable="true"], [contenteditable="true"], textarea'
                    has_input = False
                    try:
                        page.wait_for_selector(input_selector, timeout=8000)
                        has_input = True
                    except Exception:
                        has_input = False

                    is_unauth = False
                    if not has_input:
                        if "accounts.google.com" in page.url:
                            is_unauth = True
                        else:
                            sign_in_btns = page.query_selector_all('a[href*="accounts.google.com/signin"], a[href*="accounts.google.com/ServiceLogin"], a:has-text("Sign in"), a:has-text("登录"), button:has-text("Sign in"), button:has-text("登录")')
                            if len(sign_in_btns) > 0:
                                is_unauth = True

                    if is_unauth:
                        logs.append("【拦截告警】检测到账号未在 Gemini 网页版登录或 Google 登录态已失效！")
                        return {
                            "success": False,
                            "pid": os.getpid(),
                            "error_code": "AUTH_EXPIRED",
                            "error_message": f"Gemini 网页版未登录或会话已过期 (Profile: {profile.name})。请在控制台【账号管理】点击【🌐 登录 Gemini 网页版】完成登录授权，登录后请关闭弹出的 Chrome 窗口。",
                            "output_video_path": None,
                            "logs": "\n".join(logs)
                        }

                    # 3. 定位输入框
                    input_el = page.query_selector(input_selector)
                    if not input_el:
                        logs.append("未能找到输入框，正在分析页面结构...")
                        for err_sel in ["div[role='alert']", ".error-message", "gemini-quota-banner"]:
                            el = page.query_selector(err_sel)
                            if el and el.is_visible():
                                txt = el.inner_text().lower()
                                if any(k in txt for k in ["quota", "limit", "额度", "上限"]):
                                    return {
                                        "success": False,
                                        "pid": os.getpid(),
                                        "error_code": "QUOTA_EXHAUSTED",
                                        "error_message": f"检测到 Gemini 页面明确提示额度或频率限制 (Profile: {profile.name})",
                                        "output_video_path": None,
                                        "logs": "\n".join(logs)
                                    }
                        return {
                            "success": False,
                            "pid": os.getpid(),
                            "error_code": "ELEMENT_NOT_FOUND",
                            "error_message": "未在页面找到 Gemini 输入框，可能界面更新或处于非对话状态",
                            "output_video_path": None,
                            "logs": "\n".join(logs)
                        }

                    # 4. 原生画幅比例设置 (Landscape 16:9 vs Portrait 9:16)
                    aspect = getattr(task, "aspect_ratio", "16:9") or "16:9"
                    try:
                        aspect_btn = page.query_selector('button:has-text("Landscape"), button:has-text("Portrait"), button:has-text("16:9"), button:has-text("9:16")')
                        if aspect_btn and aspect_btn.is_visible():
                            btn_text = aspect_btn.inner_text()
                            need_switch = False
                            target_kw = "Landscape (16:9)" if aspect == "16:9" else "Portrait (9:16)"
                            if aspect == "9:16" and "portrait" not in btn_text.lower():
                                need_switch = True
                            elif aspect == "16:9" and "landscape" not in btn_text.lower():
                                need_switch = True
                            
                            if need_switch:
                                logs.append(f"检测到原生比例调节按钮 (当前: {btn_text.strip()})，正在切换至目标比例 [{target_kw}]...")
                                aspect_btn.click(force=True)
                                page.wait_for_timeout(600)
                                opt = page.query_selector(f'[role="menuitem"]:has-text("{target_kw}"), [role="option"]:has-text("{target_kw}"), mat-option:has-text("{target_kw}"), span:has-text("{target_kw}")')
                                if opt and opt.is_visible():
                                    opt.click(force=True)
                                    logs.append(f"成功将画幅切换为: {target_kw}")
                                    page.wait_for_timeout(500)
                                else:
                                    logs.append(f"未直接点击到 [{target_kw}] 选项，关闭菜单继续")
                                    page.keyboard.press("Escape")
                            else:
                                logs.append(f"当前画幅设置已与任务目标匹配: {btn_text.strip()}")
                    except Exception as ae:
                        logs.append(f"画幅设置容错处理: {ae}")

                    # 5. 原生模型选择 (Flash vs 3.8 Flash vs 3.1 Pro 等)
                    model_info = getattr(task, "model", "auto") or "auto"
                    if model_info and model_info != "auto":
                        try:
                            model_btn = page.query_selector('button:has-text("Flash"), button:has-text("Pro"), button[aria-label*="model"], [data-test-id="model-selector-button"]')
                            if model_btn and model_btn.is_visible():
                                logs.append(f"正在匹配 Gemini 页面模型选择 [{model_info}] ...")
                                model_btn.click(force=True)
                                page.wait_for_timeout(800)
                                kw = "3.8" if "3.8" in model_info else ("pro" if "pro" in model_info.lower() else ("flash" if "flash" in model_info.lower() else model_info))
                                opt_el = page.query_selector(f'[role="menuitem"]:has-text("{kw}"), [role="option"]:has-text("{kw}"), mat-option:has-text("{kw}"), button:has-text("{kw}")')
                                if opt_el and opt_el.is_visible():
                                    opt_el.click(force=True)
                                    logs.append(f"已成功切换模型至目标模式 [{kw}]")
                                    page.wait_for_timeout(800)
                                else:
                                    logs.append(f"模型下拉选项中未直接匹配到 [{kw}]，已采用默认就绪模型")
                                    page.keyboard.press("Escape")
                        except Exception as me:
                            logs.append(f"切换模型提示 (不阻断主流程): {me}")

                    # 6. 如果有多模态素材输入 (参考视频或参考图)，附加素材到 Gemini 输入框
                    media_files = []
                    if getattr(task, "input_video_path", None) and Path(task.input_video_path).exists():
                        ref_video = Path(task.input_video_path).resolve()
                        media_files.append(str(ref_video))
                        logs.append(f"正在准备附加多模态参考视频素材: {ref_video.name}")

                    if task.start_image_path and Path(task.start_image_path).exists():
                        ref_img = Path(task.start_image_path).resolve()
                        media_files.append(str(ref_img))
                        logs.append(f"正在准备附加参考图素材: {ref_img.name}")

                    if media_files:
                        file_input = page.query_selector('input[type="file"]')
                        if file_input:
                            file_input.set_input_files(media_files)
                            logs.append(f"已通过文件输入口上传多模态素材: {[Path(m).name for m in media_files]}")
                            page.wait_for_timeout(3500)
                        else:
                            logs.append("未发现独立 file input，尝试通过提示词上下文协同")

                    # 7. 填充提示词并安全提交
                    final_prompt = task.prompt.strip()
                    self._dismiss_overlays(page, logs)

                    # 聚焦并输入，避免被浮层截获 pointer events
                    input_el.scroll_into_view_if_needed()
                    input_el.click(force=True)
                    page.wait_for_timeout(300)
                    input_el.fill(final_prompt)
                    logs.append(f"已填入生成提示词: {final_prompt} (引擎: Gemini网页版, 指定模型: {model_info}, 画幅: {aspect})")
                    page.wait_for_timeout(1000)

                    # 发送提交
                    send_selectors = [
                        'button[aria-label="Send message"]',
                        'button[aria-label*="Send"]',
                        'button[aria-label*="发送"]',
                        '.send-button-container button',
                        '[data-test-id="send-button"]',
                        'button.send-button'
                    ]
                    submitted = False
                    for s_sel in send_selectors:
                        s_btn = page.query_selector(s_sel)
                        if s_btn and s_btn.is_visible():
                            try:
                                s_btn.click(force=True)
                                submitted = True
                                logs.append(f"已成功通过发送按钮 ({s_sel}) 提交生成任务")
                                break
                            except Exception:
                                pass
                    if not submitted:
                        page.keyboard.press("Enter")
                        logs.append("已通过回车键 (Enter) 提交任务")

                    page.wait_for_timeout(3000)

                    # 8. 智能轮询等待视频渲染结果
                    logs.append("任务已提交，开始轮询等待视频生成渲染结果...")
                    start_wait_t = time.time()
                    video_found = False

                    while (time.time() - start_wait_t) < self.timeout_sec:
                        time.sleep(4.0)
                        elapsed = int(time.time() - start_wait_t)

                        # A. 检查额度与频控提示
                        for err_sel in ["gemini-quota-banner", ".quota-exceeded-message", "div[role='alert']", "model-response:last-child"]:
                            el = page.query_selector(err_sel)
                            if el and el.is_visible():
                                txt = el.inner_text().lower()
                                if any(k in txt for k in ["quota exceeded", "reached your limit", "额度已达上限", "今日额度已用完", "try again tomorrow", "limit for today"]):
                                    logs.append("【额度耗尽】捕获到 Gemini 真实可见额度上限提示")
                                    return {
                                        "success": False,
                                        "pid": os.getpid(),
                                        "error_code": "QUOTA_EXHAUSTED",
                                        "error_message": f"Gemini 今日生成额度已达上限 (Profile: {profile.name})，系统已自动换号。",
                                        "output_video_path": None,
                                        "logs": "\n".join(logs)
                                    }
                                if any(k in txt for k in ["too many requests", "rate limit", "请求过于频繁", "请稍后再试"]):
                                    logs.append("【频控拦截】捕获到 Gemini 真实可见频控提示")
                                    return {
                                        "success": False,
                                        "pid": os.getpid(),
                                        "error_code": "RATE_LIMITED",
                                        "error_message": f"Gemini 请求频控保护 (Profile: {profile.name})，系统将自动切入冷却并换号。",
                                        "output_video_path": None,
                                        "logs": "\n".join(logs)
                                    }

                        # B. 检查是否有明确的文本拒答（提前阻断，杜绝无休止死等）
                        model_responses = page.query_selector_all("model-response")
                        if len(model_responses) > 0:
                            last_resp = model_responses[-1]
                            last_txt = last_resp.inner_text().strip()
                            # 如果回答已结束且包含拒答词
                            refusal_keywords = [
                                "无法直接生成视频", "作为语言模型", "我不能生成视频", "我无法制作视频",
                                "i cannot create videos", "i am unable to generate video", "i can't generate video",
                                "i cannot generate video", "don't have the ability to generate video"
                            ]
                            is_refusal = any(rw in last_txt.lower() for rw in refusal_keywords)
                            if is_refusal:
                                logs.append(f"【智能拒答阻断】Gemini 明确返回了文本拒答: {last_txt[:100]}...")
                                return {
                                    "success": False,
                                    "pid": os.getpid(),
                                    "error_code": "FEATURE_REFUSED",
                                    "error_message": f"Gemini 网页端当前账号回复了纯文本拒答而非视频内容。建议切换至更成熟的 Google Flow (Veo) 引擎直接生成成片视频。",
                                    "output_video_path": None,
                                    "logs": "\n".join(logs)
                                }

                        # C. 检查生成的 video 元素
                        videos = page.query_selector_all('video')
                        for v in videos:
                            src = v.get_attribute("src")
                            if src and (src.startswith("http") or src.startswith("blob:")):
                                logs.append(f"发现生成的视频元素: src={src[:80]}...")
                                logs.append("正在提取完整视频成片...")
                                try:
                                    b64_data = page.evaluate("""
                                        async (video) => {
                                            try {
                                                const res = await fetch(video.src, { credentials: 'include' });
                                                if (!res.ok) return null;
                                                const blob = await res.blob();
                                                return new Promise((resolve) => {
                                                    const reader = new FileReader();
                                                    reader.onloadend = () => resolve(reader.result);
                                                    reader.readAsDataURL(blob);
                                                });
                                            } catch (err) {
                                                return null;
                                            }
                                        }
                                    """, v)
                                    if b64_data and "," in b64_data:
                                        raw_bytes = base64.b64decode(b64_data.split(",", 1)[1])
                                        if len(raw_bytes) > 20000 and not raw_bytes.startswith(b"<!doctype") and not raw_bytes.startswith(b"<html"):
                                            with open(output_video_path, "wb") as vf:
                                                vf.write(raw_bytes)
                                            logs.append(f"已成功通过浏览器安全上下文转存成片 ({len(raw_bytes)} 字节): {output_video_path}")
                                            video_found = True
                                            break
                                        else:
                                            logs.append(f"上下文返回内容未就绪 (大小: {len(raw_bytes)} 字节)，继续等待渲染...")
                                except Exception as e_ev:
                                    logs.append(f"页面内视频流提取提示: {e_ev}")

                        # D. 兜底方案：通过页面原生下载按钮
                        if not video_found:
                            dl_btns = page.query_selector_all("a[download], button[aria-label*='Download video'], button[aria-label*='Download'], button[aria-label*='下载视频']")
                            if dl_btns and len(dl_btns) > 0:
                                dl_btn = dl_btns[-1]
                                if dl_btn.is_visible():
                                    try:
                                        logs.append("检测到成片下载按钮，尝试直接触发原生文件下载...")
                                        with page.expect_download(timeout=8000) as dl_info:
                                            dl_btn.click(force=True)
                                        download = dl_info.value
                                        download.save_as(str(output_video_path))
                                        if output_video_path.exists() and output_video_path.stat().st_size > 20000:
                                            logs.append(f"已成功通过下载通道获取成片 ({output_video_path.stat().st_size} 字节)")
                                            video_found = True
                                            break
                                    except Exception as de:
                                        logs.append(f"原生下载尝试提示: {de}")

                        if video_found:
                            break

                        if elapsed % 20 == 0:
                            logs.append(f"等待生成中... 已耗时 {elapsed}s")

                    if video_found and output_video_path.exists() and output_video_path.stat().st_size > 1024:
                        return {
                            "success": True,
                            "pid": os.getpid(),
                            "error_code": None,
                            "error_message": None,
                            "output_video_path": str(output_video_path.resolve()),
                            "logs": "\n".join(logs)
                        }
                    else:
                        logs.append("超时或未捕获到生成的视频流")
                        return {
                            "success": False,
                            "pid": os.getpid(),
                            "error_code": "VIDEO_GEN_TIMEOUT",
                            "error_message": f"Gemini 视频生成超时或未能在页面提取到视频元素 (耗时: {self.timeout_sec}s)",
                            "output_video_path": None,
                            "logs": "\n".join(logs)
                        }

                finally:
                    browser.close()
                    logs.append("浏览器会话已安全退出。")

        except Exception as exc:
            logs.append(f"执行异常: {exc}")
            err_str = str(exc)
            err_code = "EXCEPTION"
            if any(k in err_str.lower() for k in ["target closed", "browser has been closed", "singleton", "lock", "in use", "already running"]):
                err_code = "PROFILE_LOCKED"
                err_str = f"Chrome Profile 目录被独占占用 ({profile.name})。通常是因为此前点击【登录】打开的 Chrome 窗口尚未关闭。请先关闭 Chrome 窗口再重试。"
            return {
                "success": False,
                "pid": os.getpid(),
                "error_code": err_code,
                "error_message": err_str,
                "output_video_path": None,
                "logs": "\n".join(logs)
            }

    def _synthesize_tts_file(self, text: str, voice: str, out_path: Path) -> bool:
        """本地配音功能已下线"""
        return False

    def _extract_narration_script(self, text: str) -> str:
        """从 Gemini 多模态输出中智能提取最纯粹的解说文案，去除思考过程与舞台说明、去除 Markdown 格式"""
        import re
        if not text:
            return ""
        clean = text.strip()
        if clean.startswith("Gemini said"):
            clean = clean[len("Gemini said"):].strip()

        extracted_block = None
        for tag in ["【配音解说词】", "[配音解说词]", "配音解说词：", "配音解说词:"]:
            if tag in clean:
                parts = clean.split(tag, 1)
                extracted_block = parts[1].strip()
                break
        else:
            if "配音解说词" in clean:
                parts = clean.split("配音解说词", 1)
                extracted_block = parts[1].lstrip("：:\n ").strip()

        if extracted_block:
            block_lines = []
            for line in extracted_block.split("\n"):
                s_line = line.strip()
                if s_line.startswith("#") or s_line.startswith("===") or s_line.startswith("---"):
                    break
                if s_line:
                    block_lines.append(s_line)
            if block_lines:
                extracted_clean = " ".join(block_lines)
            else:
                extracted_clean = extracted_block
            quotes = re.findall(r'[“]([^”]+)[”]', extracted_clean)
            if quotes:
                script = " ".join(quotes)
            else:
                script = extracted_clean
        else:
            # 没有专门配音解说词标识时，清理 Markdown 标签与元数据
            script = re.sub(r'[*#_`~>\[\]]', '', clean)
            script = re.sub(r'https?://\S+', '', script)

        # 清除括号内的动作/镜头说明
        script = re.sub(r'[\(（][^\)）]*[\)）]', '', script).strip()
        script = script.strip('“"”\' \n\r')
        return script if len(script) >= 2 else text[:200]

    def execute_audio_task(self, task: Task, profile: Profile) -> Dict[str, Any]:
        """本地配音功能已下线"""
        return {
            "success": False,
            "pid": os.getpid(),
            "error_code": "AUDIO_DISABLED",
            "error_message": "本地配音功能已下线",
            "output_audio_path": None,
            "logs": "本地配音功能已下线并移除"
        }

    def execute_multimodal_interaction(
        self,
        profile: Profile,
        prompt: str,
        mode: str = "chat",
        video_path: Optional[str] = None,
        image_path: Optional[str] = None,
        voice: str = "zh-CN-YunxiNeural",
        aspect_ratio: str = "16:9",
        timeout_sec: int = 120
    ) -> Dict[str, Any]:
        """
        Gemini 网页端综合多模态交互工作台：
        - 支持文字对话、多轮交互
        - 支持上传任意本地视频 (.mp4, .mov 等)，让 Gemini 网页端分析画面并生成配音文案与音频
        - 支持 AI 绘画（文生图/图生图），自动提取生成的图片并转存到资产库
        - 采用稳定 Playwright 驱动，内置自动解除 Profile 锁、 Quilling 键盘输入及 Agree 协议确认
        """
        worker_name = threading.current_thread().name
        profile_dir = self._resolve_profile_dir(profile)
        out_id = uuid.uuid4().hex[:12]
        output_audio_path = self.output_dir / f"gemini_audio_{out_id}.mp3"
        output_images = []
        logs = []

        logs.append(f"[{worker_name}] 启动 Gemini 多模态工作台交互 (Profile: {profile.name}, Mode: {mode})")
        logs.append(f"Prompt: {prompt[:80] if prompt else '（无提示词）'}")

        if not profile_dir.exists():
            profile_dir.mkdir(parents=True, exist_ok=True)

        prof_lock = get_profile_lock(profile.name)
        acquired = prof_lock.acquire(timeout=90)
        if not acquired:
            return {
                "success": False,
                "error_code": "PROFILE_BUSY",
                "error_message": f"账号 [{profile.name}] 当前正在执行前序对话，请稍候片刻再试。",
                "text": "",
                "audio_url": None,
                "image_urls": [],
                "logs": f"[{worker_name}] 获取账号锁超时"
            }

        try:
            # 独占锁保障下，安全排查并清理属于当前账号的孤儿僵尸进程
            unlock_profile_processes(profile_dir, profile.name)

            has_video = bool(video_path and Path(video_path).exists())
            has_image = bool(image_path and Path(image_path).exists())
            if has_video:
                logs.append(f"已附加本地参考视频: {Path(video_path).name}")
            if has_image:
                logs.append(f"已附加本地参考图片: {Path(image_path).name}")

            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                launch_args = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
                logs.append("正在拉起独立 Chrome 容器 (Profile 隔离模式)...")
                try:
                    browser = p.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir.resolve()),
                        channel="chrome",
                        headless=self.headless,
                        args=launch_args
                    )
                    with self._sessions_lock:
                        self._active_sessions[task.id] = {
                            "browser": browser,
                            "profile": profile,
                            "cancelled": False
                        }
                except Exception as launch_exc:
                    lexc_str = str(launch_exc).lower()
                    logs.append(f"拉起浏览器异常: {launch_exc}")
                    if any(k in lexc_str for k in ["target closed", "browser has been closed", "singleton", "lock", "in use", "already running"]):
                        return {
                            "success": False,
                            "error_code": "PROFILE_LOCKED",
                            "error_message": f"Profile [{profile.name}] 正在被运行中的 Chrome 窗口占用。请在桌面关闭 Chrome 窗口或在控制台点击【⏹ 释放占用】后重试。",
                            "text": "",
                            "audio_url": None,
                            "image_urls": [],
                            "logs": "\n".join(logs)
                        }
                    raise launch_exc

                try:
                    page = browser.new_page()
                    logs.append("正在导航至 Gemini 主工作区 https://gemini.google.com/app ...")
                    try:
                        page.goto("https://gemini.google.com/app", timeout=35000)
                    except Exception as ge:
                        logs.append(f"页面初次加载提醒: {ge}")

                    page.wait_for_timeout(2500)
                    self._dismiss_overlays(page, logs)

                    # 记录初始回复节点数量，避免读到历史旧对话
                    initial_resp_count = len(page.query_selector_all('model-response'))

                    # 检查输入框与登录态
                    input_selector = 'rich-textarea div[contenteditable="true"], div.ql-editor[contenteditable="true"], [contenteditable="true"], textarea'
                    has_input = False
                    try:
                        page.wait_for_selector(input_selector, timeout=8000)
                        has_input = True
                    except Exception:
                        has_input = False

                    if not has_input:
                        logs.append("未检测到有效输入框，可能未登录或被弹窗拦截")
                        return {
                            "success": False,
                            "error_code": "AUTH_EXPIRED",
                            "error_message": f"Gemini 网页版未登录或会话已过期 (Profile: {profile.name})。请在顶部点击【🌐 登录网页版】完成 Google 登录授权。",
                            "text": "",
                            "audio_url": None,
                            "image_urls": [],
                            "logs": "\n".join(logs)
                        }

                    input_el = page.query_selector(input_selector)

                    # 上传多模态文件附件
                    if has_video or has_image:
                        upload_btn = page.query_selector('button[aria-label="Upload & tools"], button[aria-label*="Upload"], button[aria-label*="Add"], button:has-text("+")')
                        if upload_btn:
                            upload_btn.click(force=True)
                            page.wait_for_timeout(1000)

                        file_input = page.query_selector('input[type="file"]')
                        if has_video and has_image:
                            v_res = str(Path(video_path).resolve())
                            i_res = str(Path(image_path).resolve())
                            if file_input:
                                try:
                                    file_input.set_input_files([v_res, i_res])
                                    logs.append(f"已同时上传视频与图片素材: {Path(video_path).name}, {Path(image_path).name}")
                                except Exception:
                                    file_input.set_input_files(v_res)
                                    logs.append(f"已上传视频素材: {Path(video_path).name}")
                                for _ in range(35):
                                    page.wait_for_timeout(1000)
                                    chips = page.query_selector_all('uploader-file-preview, [class*="file-preview"]')
                                    spinners = page.query_selector_all('uploader-file-preview mat-spinner, uploader-file-preview [role="progressbar"], uploader-file-preview .loading')
                                    if len(chips) > 0 and len(spinners) == 0:
                                        logs.append("多模态附件上传与预处理完成！")
                                        break
                        elif has_video:
                            v_res = str(Path(video_path).resolve())
                            if file_input:
                                file_input.set_input_files(v_res)
                                logs.append(f"已上传视频素材: {Path(video_path).name}，正在等待 Gemini 网页端解析处理...")
                                for _ in range(35):
                                    page.wait_for_timeout(1000)
                                    chips = page.query_selector_all('uploader-file-preview, [class*="file-preview"]')
                                    spinners = page.query_selector_all('uploader-file-preview mat-spinner, uploader-file-preview [role="progressbar"], uploader-file-preview .loading')
                                    if len(chips) > 0 and len(spinners) == 0:
                                        logs.append("视频上传与预处理完成！")
                                        break
                        elif has_image:
                            i_res = str(Path(image_path).resolve())
                            img_inputs = page.query_selector_all('input[type="file"][accept*="image"], input[type="file"]')
                            target_inp = img_inputs[0] if img_inputs else file_input
                            if target_inp:
                                target_inp.set_input_files(i_res)
                                logs.append(f"已上传参考图片素材: {Path(image_path).name}")
                                page.wait_for_timeout(2000)

                    # 整理提示词
                    clean_prompt = prompt.strip() if prompt else ""
                    if mode == "image":
                        if not any(k in clean_prompt for k in ["画", "draw", "image", "插画", "图"]):
                            clean_prompt = f"画一张插画：{clean_prompt}"
                    elif has_video and not clean_prompt:
                        clean_prompt = "请深度分析我提供的视频画面内容、镜头运镜与动作节奏，提炼核心看点并给出专业总结。"

                    # 填写内容（使用 execCommand insertText 富文本原子插入，支持多行上下文且避免 \n 触发换行过早发送）
                    if clean_prompt and input_el:
                        input_el.scroll_into_view_if_needed()
                        input_el.click(force=True)
                        page.wait_for_timeout(200)
                        inserted = page.evaluate("""(txt) => {
                            const el = document.querySelector('rich-textarea div[contenteditable="true"]');
                            if (el) {
                                el.focus();
                                return document.execCommand('insertText', false, txt);
                            }
                            return false;
                        }""", clean_prompt)
                        if not inserted:
                            page.keyboard.insert_text(clean_prompt)
                        logs.append(f"已输入提示词 ({len(clean_prompt)} 字): {clean_prompt[:60]}...")
                        page.wait_for_timeout(500)

                    # 发送请求
                    send_selectors = [
                        'button[aria-label="Send message"]',
                        'button[aria-label*="Send"]',
                        'button[aria-label*="发送"]',
                        '.send-button-container button',
                        '[data-test-id="send-button"]'
                    ]
                    submitted = False
                    for s_sel in send_selectors:
                        s_btn = page.query_selector(s_sel)
                        if s_btn and s_btn.is_visible() and s_btn.is_enabled():
                            s_btn.click(force=True)
                            submitted = True
                            logs.append("已点击发送按钮提交多模态请求")
                            break
                    if not submitted:
                        page.keyboard.press("Enter")
                        logs.append("已通过 Enter 键提交多模态请求")

                    page.wait_for_timeout(1000)

                    # 检测并点击视频协议提示弹窗 (A reminder about creating videos -> Agree)
                    agree_btns = page.query_selector_all('button:has-text("Agree"), button:has-text("同意"), button:has-text("I agree")')
                    for ab in agree_btns:
                        if ab.is_visible():
                            logs.append("检测到视频创建协议弹窗，自动点击同意授权...")
                            ab.click(force=True)
                            page.wait_for_timeout(1000)
                            break

                    # 等待模型回复
                    logs.append("等待 Gemini 响应流...")
                    start_t = time.time()
                    generation_started = False
                    captured_text = ""
                    last_txt = ""
                    stable_count = 0

                    while (time.time() - start_t) < max(timeout_sec, 90):
                        time.sleep(1.0)
                        # 循环中持续检测视频协议弹窗
                        agree_btns = page.query_selector_all('button:has-text("Agree"), button:has-text("同意"), button:has-text("I agree")')
                        for ab in agree_btns:
                            if ab.is_visible():
                                logs.append("检测到视频创建协议弹窗，自动点击同意授权...")
                                ab.click(force=True)
                                page.wait_for_timeout(500)
                                break

                        stop_btn = page.query_selector('button[aria-label*="Stop"], button[aria-label*="停止"]')
                        model_responses = page.query_selector_all("model-response")
                        if stop_btn or len(model_responses) > initial_resp_count:
                            generation_started = True

                        elapsed = int(time.time() - start_t)
                        if elapsed % 15 == 0:
                            logs.append(f"[{elapsed}s] 等待回复生成中... (节点数: {len(model_responses)}, 生成标志: {bool(stop_btn)})")

                        if generation_started and not stop_btn and len(model_responses) > 0:
                            last_resp = model_responses[-1]
                            txt = last_resp.inner_text().strip()
                            if txt.startswith("Gemini said"):
                                txt = txt[len("Gemini said"):].strip()
                            if "You stopped this response" in txt:
                                continue
                            has_images = bool(last_resp.query_selector("img"))
                            if len(txt) > 0 or has_images:
                                if not txt and has_images:
                                    txt = f"已为您生成 AI 绘画作品：{prompt or '参考插画'}"
                                if txt == last_txt:
                                    stable_count += 1
                                    if stable_count >= 3:
                                        captured_text = txt
                                        logs.append(f"Gemini 回答已完全稳定输出: {len(captured_text)} 字符 (生成图片: {has_images})")
                                        break
                                else:
                                    stable_count = 0
                                    last_txt = txt

                    if not captured_text:
                        return {
                            "success": False,
                            "error_code": "RESPONSE_TIMEOUT",
                            "error_message": f"Gemini 响应超时（已等待 {int(time.time() - start_t)} 秒），未获取到有效回答。请检查网络或重新提问。",
                            "text": "",
                            "audio_url": None,
                            "image_urls": [],
                            "profile_id": profile.id,
                            "profile_name": profile.name,
                            "logs": "\n".join(logs)
                        }

                    # 检查图片产物 (如果是绘画模式或包含生图)
                    if mode == "image" or any(k in clean_prompt for k in ["画", "生图", "image", "插画"]) or (model_responses and model_responses[-1].query_selector("img")):
                        page.wait_for_timeout(2500)
                        target_resp = model_responses[-1] if model_responses else page
                        img_elems = target_resp.query_selector_all("img, .generated-image img, .image-container img")
                        for idx, im in enumerate(img_elems):
                            box = im.bounding_box()
                            if box and (box['width'] < 80 or box['height'] < 80):
                                continue
                            img_save_path = self.output_dir / f"gemini_img_{out_id}_{idx}.png"
                            saved = False
                            # 优先尝试从原图 Blob / Fetch 提取全分辨率原图数据
                            try:
                                b64_data = page.evaluate("""
                                    async (img) => {
                                        try {
                                            const res = await fetch(img.src);
                                            const blob = await res.blob();
                                            return new Promise((resolve) => {
                                                const reader = new FileReader();
                                                reader.onloadend = () => resolve(reader.result);
                                                reader.readAsDataURL(blob);
                                            });
                                        } catch (e) { return null; }
                                    }
                                """, im)
                                if b64_data and "," in b64_data:
                                    raw = base64.b64decode(b64_data.split(",", 1)[1])
                                    if len(raw) > 1000:
                                        with open(img_save_path, "wb") as f:
                                            f.write(raw)
                                        output_images.append(f"/media/outputs/{img_save_path.name}")
                                        logs.append(f"Blob原生提取高清原图成功: {img_save_path.name} (大小: {len(raw)} 字节)")
                                        saved = True
                            except Exception as ie:
                                logs.append(f"Blob提取原图异常，切换截图备选: {ie}")

                            # 备选方案：若 Blob 提取因跨域/限制失败，使用 Playwright 元素精准截图
                            if not saved:
                                try:
                                    im.screenshot(path=str(img_save_path))
                                    if img_save_path.exists() and img_save_path.stat().st_size > 1000:
                                        output_images.append(f"/media/outputs/{img_save_path.name}")
                                        logs.append(f"元素截图提取图片备选成功: {img_save_path.name} (大小: {img_save_path.stat().st_size} 字节)")
                                        saved = True
                                except Exception as se:
                                    logs.append(f"元素截图提取失败: {se}")

                    # 本地配音功能已下线，纯净返回 AI 文本与视觉产物
                    audio_url = None
                    audio_path_str = None
                    final_text = captured_text
                    return {
                        "success": True,
                        "text": final_text,
                        "audio_url": audio_url,
                        "audio_path": audio_path_str,
                        "image_urls": output_images,
                        "profile_id": profile.id,
                        "profile_name": profile.name,
                        "logs": "\n".join(logs)
                    }

                finally:
                    with self._sessions_lock:
                        self._active_sessions.pop(task.id, None)
                    try:
                        browser.close()
                    except Exception:
                        pass
                    unlock_profile_processes(profile_dir, profile.name)
                    logs.append("Chrome 进程已安全回收，锁文件已清理，系统内存已释放。")

        except Exception as exc:
            logs.append(f"执行 Gemini 多模态交互异常: {exc}")
            unlock_profile_processes(profile_dir, profile.name)
            return {
                "success": False,
                "error_code": "EXCEPTION",
                "error_message": str(exc),
                "text": "",
                "audio_url": None,
                "image_urls": [],
                "logs": "\n".join(logs)
            }
        finally:
            prof_lock.release()
