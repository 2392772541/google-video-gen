from __future__ import annotations
import os
import sys
import time
import json
import base64
import urllib.request
import threading
from pathlib import Path
from typing import Dict, Any, Optional

from .models import Task, Profile

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
                    "--disable-blink-features=AutomationControlled",
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

                    # 6. 如果有参考图输入，附加参考图
                    if task.start_image_path and Path(task.start_image_path).exists():
                        ref_img = Path(task.start_image_path).resolve()
                        logs.append(f"正在准备附加参考图素材: {ref_img.name}")
                        file_input = page.query_selector('input[type="file"]')
                        if file_input:
                            file_input.set_input_files(str(ref_img))
                            logs.append("已通过文件输入口上传参考图")
                            page.wait_for_timeout(2000)
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
