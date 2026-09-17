from __future__ import annotations
import os
import sys
import time
import json
import urllib.request
import threading
from pathlib import Path
from typing import Dict, Any, Optional

from .models import Task, Profile

class GeminiWebWorker:
    """
    Worker for orchestrating video generation on gemini.google.com via persistent Chrome profiles.
    - Zero cookie leakage: uses local isolated Chrome profile directories.
    - Automatic error classification: PROFILE_LOCKED, AUTH_EXPIRED, QUOTA_EXHAUSTED, RATE_LIMITED.
    - Automatic downloading and saving of generated videos.
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
        # Default gflow / chrome profile location
        appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(appdata) / "ffroliva" / "gflow-cli" / f"profile_{profile.name}"

    def execute_task(self, task: Task, profile: Profile) -> Dict[str, Any]:
        worker_name = threading.current_thread().name
        profile_dir = self._resolve_profile_dir(profile)
        
        logs = []
        logs.append(f"[{worker_name}] 启动 Gemini 网页版生成引擎 (Profile: {profile.name})")
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
                    logs.append("正在打开 https://gemini.google.com/app ...")
                    page.goto("https://gemini.google.com/app", timeout=35000)
                    page.wait_for_timeout(3000)

                    cur_url = page.url
                    page_title = page.title()
                    logs.append(f"页面加载完成: Title='{page_title}', URL='{cur_url}'")

                    # 1. 登录状态核验：优先寻找对话输入框
                    input_selector = 'div.ql-editor[contenteditable="true"], rich-textarea div[contenteditable="true"], textarea'
                    has_input = False
                    try:
                        page.wait_for_selector(input_selector, timeout=8000)
                        has_input = True
                    except Exception:
                        has_input = False

                    is_unauth = False
                    if not has_input:
                        if "accounts.google.com" in cur_url:
                            is_unauth = True
                        else:
                            # 仅在页面明确包含登录入口按钮且无输入框时认定为未登录
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

                    # 2. 定位聊天输入框
                    try:
                        if not has_input:
                            page.wait_for_selector(input_selector, timeout=12000)
                    except Exception:
                        logs.append("未能找到输入框，正在分析页面结构...")
                        # 检查是否有可见的错误警告
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

                    # 3. 如果有参考图输入，附加参考图
                    if task.start_image_path and Path(task.start_image_path).exists():
                        ref_img = Path(task.start_image_path).resolve()
                        logs.append(f"正在准备附加参考图素材: {ref_img.name}")
                        file_input = page.query_selector('input[type="file"]')
                        if file_input:
                            file_input.set_input_files(str(ref_img))
                            logs.append("已通过文件输入口上传参考图")
                            page.wait_for_timeout(2000)
                        else:
                            logs.append("未发现独立 file input，尝试剪贴板或直接提示词附带说明")

                    # 4. 填充提示词并提交
                    input_el = page.query_selector(input_selector)
                    if input_el:
                        # 构造增强提示词
                        final_prompt = task.prompt.strip()
                        if not any(k in final_prompt.lower() for k in ["video", "视频", "veo", "生视频", "生成视频"]):
                            final_prompt = f"生成一段9:16竖屏短视频：{final_prompt}"

                        input_el.click()
                        input_el.fill(final_prompt)
                        logs.append(f"已填入生成提示词: {final_prompt}")
                        page.wait_for_timeout(1000)

                        # 发送消息
                        send_btn = page.query_selector('button[aria-label*="Send"], button[aria-label*="发送"], .send-button')
                        if send_btn and send_btn.is_enabled():
                            send_btn.click()
                            logs.append("已点击发送按钮提交生成任务")
                        else:
                            page.keyboard.press("Enter")
                            logs.append("已通过回车键提交任务")
                    else:
                        return {
                            "success": False,
                            "pid": os.getpid(),
                            "error_code": "INPUT_ERROR",
                            "error_message": "未能激活 Gemini 输入框",
                            "output_video_path": None,
                            "logs": "\n".join(logs)
                        }

                    # 5. 等待视频生成完毕并捕获视频元素
                    logs.append("任务已提交，开始轮询等待视频生成渲染结果...")
                    start_wait_t = time.time()
                    video_found = False

                    while (time.time() - start_wait_t) < self.timeout_sec:
                        time.sleep(3.0)
                        elapsed = int(time.time() - start_wait_t)

                        # 检查是否有真实可见的异常提示（仅检查可见 DOM 节点，禁止全量 HTML 字符串盲匹）
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

                        # 检查是否有新生成的 video 元素
                        videos = page.query_selector_all('video')
                        for v in videos:
                            src = v.get_attribute("src")
                            if src and (src.startswith("http") or src.startswith("blob:")):
                                logs.append(f"发现生成的视频元素: src={src[:80]}...")
                                logs.append("正在通过已登录浏览器安全上下文提取完整视频流...")
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
                                        import base64
                                        raw_bytes = base64.b64decode(b64_data.split(",", 1)[1])
                                        if len(raw_bytes) > 20000 and not raw_bytes.startswith(b"<!doctype") and not raw_bytes.startswith(b"<html"):
                                            with open(output_video_path, "wb") as vf:
                                                vf.write(raw_bytes)
                                            logs.append(f"已成功通过浏览器安全上下文转存成片 ({len(raw_bytes)} 字节): {output_video_path}")
                                            video_found = True
                                            break
                                        else:
                                            logs.append(f"上下文返回内容未就绪或为错误页 (大小: {len(raw_bytes)} 字节)，继续等待渲染...")
                                except Exception as e_ev:
                                    logs.append(f"页面内视频流提取异常: {e_ev}")

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
