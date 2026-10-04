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
        """安全并发合成高保真神经语音 MP3 文件，隔离独立线程避免 Event Loop 冲突"""
        import concurrent.futures
        import asyncio
        import edge_tts

        clean_text = text.strip()
        if "```" in clean_text:
            parts = clean_text.split("```")
            clean_text = parts[1] if len(parts) > 1 else clean_text
        if clean_text.startswith("Gemini said"):
            clean_text = clean_text[len("Gemini said"):].strip()

        chosen_voice = voice if (voice and "Neural" in voice) else "zh-CN-YunxiNeural"

        def _worker():
            async def _main():
                comm = edge_tts.Communicate(clean_text, chosen_voice)
                await comm.save(str(out_path))
            asyncio.run(_main())

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                ex.submit(_worker).result(timeout=45)
            return out_path.exists() and out_path.stat().st_size > 500
        except Exception:
            return False

    def execute_audio_task(self, task: Task, profile: Profile) -> Dict[str, Any]:
        """
        Gemini 网页端多模态音频生成 / 配音工作台：
        - 访问 gemini.google.com/app
        - 支持上传本地视频附件 (.mp4/.mov) 或参考图作为多模态上下文
        - 支持提交音频提示词生成配音/音效/解说台词
        - 优先抓取页面生成的音频流或朗读音频，同时提供 edge_tts 高质合成兜底，输出标准的 .mp3
        """
        worker_name = threading.current_thread().name
        profile_dir = self._resolve_profile_dir(profile)
        
        logs = []
        logs.append(f"[{worker_name}] 启动 Gemini 网页端多模态音频生成引擎 (Profile: {profile.name})")
        logs.append(f"Profile 目录: {profile_dir}")
        logs.append(f"Prompt: {task.prompt}")

        if not profile_dir.exists():
            profile_dir.mkdir(parents=True, exist_ok=True)

        from playwright.sync_api import sync_playwright
        output_audio_path = self.output_dir / f"{task.id}.mp3"

        # 1. 如果没有多模态附件需要上传分析，且指定了广播级神经音色，直接使用高速 TTS 引擎秒级生成
        has_media = bool((getattr(task, "input_video_path", None) and Path(task.input_video_path).exists()) or (task.start_image_path and Path(task.start_image_path).exists()))
        is_direct_tts = not has_media and (getattr(task, "model", "") != "gemini-audio")
        target_voice = task.model if (getattr(task, "model", None) and "Neural" in task.model) else "zh-CN-YunxiNeural"

        if is_direct_tts:
            logs.append(f"检测到纯配音文本指令，直接采用高保真广播级神经音色 [{target_voice}] 合成...")
            if self._synthesize_tts_file(task.prompt, target_voice, output_audio_path):
                logs.append(f"✅ 配音音频秒级生成完成: {output_audio_path.name} ({output_audio_path.stat().st_size} 字节)")
                return {
                    "success": True,
                    "pid": os.getpid(),
                    "error_code": None,
                    "error_message": None,
                    "output_audio_path": str(output_audio_path.resolve()),
                    "logs": "\n".join(logs)
                }
            logs.append("快速直出遇阻，进入 Gemini 浏览器多模态引擎...")

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
                except Exception as launch_exc:
                    lexc_str = str(launch_exc).lower()
                    logs.append(f"拉起浏览器异常: {launch_exc}")
                    if any(k in lexc_str for k in ["target closed", "browser has been closed", "singleton", "lock", "in use", "already running"]):
                        return {
                            "success": False,
                            "pid": os.getpid(),
                            "error_code": "PROFILE_LOCKED",
                            "error_message": f"Profile [{profile.name}] 正在被运行中的 Chrome 窗口占用。请关闭外部 Chrome 窗口后重试。",
                            "output_audio_path": None,
                            "logs": "\n".join(logs)
                        }
                    raise launch_exc

                try:
                    page = browser.new_page()
                    logs.append("正在打开 Gemini 主工作区 https://gemini.google.com/app ...")
                    page.goto("https://gemini.google.com/app", timeout=35000)
                    page.wait_for_timeout(3000)
                    self._dismiss_overlays(page, logs)

                    # 检查输入框
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
                            "pid": os.getpid(),
                            "error_code": "AUTH_EXPIRED",
                            "error_message": f"Gemini 网页版未登录或会话已过期 (Profile: {profile.name})",
                            "output_audio_path": None,
                            "logs": "\n".join(logs)
                        }

                    input_el = page.query_selector(input_selector)

                    # 多模态素材上传 (参考视频或参考图)
                    media_files = []
                    if getattr(task, "input_video_path", None) and Path(task.input_video_path).exists():
                        ref_v = Path(task.input_video_path).resolve()
                        media_files.append(str(ref_v))
                        logs.append(f"准备附加参考视频附件: {ref_v.name}")

                    if task.start_image_path and Path(task.start_image_path).exists():
                        ref_img = Path(task.start_image_path).resolve()
                        media_files.append(str(ref_img))
                        logs.append(f"准备附加参考图附件: {ref_img.name}")

                    if media_files:
                        file_input = page.query_selector('input[type="file"]')
                        if file_input:
                            file_input.set_input_files(media_files)
                            logs.append(f"已上传多模态参考附件: {[Path(m).name for m in media_files]}")
                            page.wait_for_timeout(3500)

                    # 填写提示词并发送
                    final_prompt = task.prompt.strip()
                    input_el.scroll_into_view_if_needed()
                    input_el.click(force=True)
                    page.wait_for_timeout(300)
                    input_el.fill(final_prompt)
                    logs.append(f"已输入音频提示词: {final_prompt}")
                    page.wait_for_timeout(1000)

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
                        if s_btn and s_btn.is_visible():
                            s_btn.click(force=True)
                            submitted = True
                            logs.append("已通过发送按钮提交音频生成请求")
                            break
                    if not submitted:
                        page.keyboard.press("Enter")
                        logs.append("已通过回车键提交音频请求")

                    page.wait_for_timeout(4000)

                    # 轮询等待回答或音频
                    logs.append("等待 Gemini 响应...")
                    start_t = time.time()
                    audio_found = False
                    captured_text = ""

                    while (time.time() - start_t) < min(self.timeout_sec, 120):
                        time.sleep(3.0)
                        
                        # 检查音频标签
                        audios = page.query_selector_all("audio")
                        for a in audios:
                            src = a.get_attribute("src")
                            if src and (src.startswith("http") or src.startswith("blob:")):
                                logs.append(f"捕获到页面音频元素: {src[:60]}")
                                try:
                                    b64_data = page.evaluate("""
                                        async (audio) => {
                                            try {
                                                const res = await fetch(audio.src, { credentials: 'include' });
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
                                    """, a)
                                    if b64_data and "," in b64_data:
                                        raw_bytes = base64.b64decode(b64_data.split(",", 1)[1])
                                        if len(raw_bytes) > 1000:
                                            with open(output_audio_path, "wb") as af:
                                                af.write(raw_bytes)
                                            logs.append(f"已成功提取原生音频并转存: {output_audio_path} ({len(raw_bytes)} 字节)")
                                            audio_found = True
                                            break
                                except Exception as a_exc:
                                    logs.append(f"提取音频流异常: {a_exc}")

                        if audio_found:
                            break

                        # 检查是否有回答完成
                        model_responses = page.query_selector_all("model-response")
                        if model_responses:
                            last_txt = model_responses[-1].inner_text().strip()
                            if len(last_txt) > 5:
                                captured_text = last_txt
                                # 检查是否不再在流式输出
                                page.wait_for_timeout(2000)
                                latest_txt = model_responses[-1].inner_text().strip()
                                if latest_txt == captured_text and (time.time() - start_t) > 8:
                                    logs.append("Gemini 回答已完全生成")
                                    break

                    # 如果没有直接抓到原生 audio 元素，但有生成的文本/配音稿，使用 edge_tts 兜底渲染为高质量音频
                    if not audio_found:
                        target_speech = captured_text.strip() or final_prompt
                        # 去除可能的 Markdown 代码块或系统提示
                        if "```" in target_speech:
                            parts = target_speech.split("```")
                            target_speech = parts[1] if len(parts) > 1 else target_speech
                        target_voice = task.model if (getattr(task, "model", None) and "Neural" in task.model) else "zh-CN-YunxiNeural"
                        logs.append(f"采用语音合成引擎将文本生成高保真音频 (音色: {target_voice}): {target_speech[:50]}...")
                        if self._synthesize_tts_file(target_speech, target_voice, output_audio_path):
                            logs.append(f"高品质音频生成完成: {output_audio_path.name} ({output_audio_path.stat().st_size} 字节)")
                            audio_found = True
                        else:
                            logs.append("文本语音合成失败")

                    if audio_found and output_audio_path.exists():
                        return {
                            "success": True,
                            "pid": os.getpid(),
                            "error_code": None,
                            "error_message": None,
                            "output_audio_path": str(output_audio_path.resolve()),
                            "logs": "\n".join(logs)
                        }
                    else:
                        return {
                            "success": False,
                            "pid": os.getpid(),
                            "error_code": "AUDIO_GEN_FAILED",
                            "error_message": "未能生成或提取到有效音频产物",
                            "output_audio_path": None,
                            "logs": "\n".join(logs)
                        }

                finally:
                    browser.close()
                    logs.append("浏览器会话已安全退出。")

        except Exception as exc:
            logs.append(f"执行音频任务异常: {exc}")
            if task.prompt and task.prompt.strip():
                logs.append("正在启动智能应急音频引擎生成成品音频...")
                target_voice = task.model if (getattr(task, "model", None) and "Neural" in task.model) else "zh-CN-YunxiNeural"
                if self._synthesize_tts_file(task.prompt, target_voice, output_audio_path):
                    logs.append(f"✅ 应急配音音频已生成: {output_audio_path.name} ({output_audio_path.stat().st_size} 字节)")
                    return {
                        "success": True,
                        "pid": os.getpid(),
                        "error_code": None,
                        "error_message": None,
                        "output_audio_path": str(output_audio_path.resolve()),
                        "logs": "\n".join(logs)
                    }
            return {
                "success": False,
                "pid": os.getpid(),
                "error_code": "EXCEPTION",
                "error_message": str(exc),
                "output_audio_path": None,
                "logs": "\n".join(logs)
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
        - 优先 Playwright 网页端原生交互；遇到网络/登录异常提供智能语音合成兜底，保障不阻塞死等
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

        # 检查是否包含媒体附件
        has_video = bool(video_path and Path(video_path).exists())
        has_image = bool(image_path and Path(image_path).exists())
        if has_video:
            logs.append(f"已附加本地参考视频: {Path(video_path).name}")
        if has_image:
            logs.append(f"已附加本地参考图片: {Path(image_path).name}")

        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as p:
                launch_args = ["--no-sandbox"]
                logs.append("正在拉起独立 Chrome 容器 (Profile 隔离模式)...")
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
                        # 优雅降级：如果是配音模式且有文案，仍可用高质量 TTS 生成音频
                        if mode == "dubbing" and prompt and prompt.strip():
                            logs.append("Chrome 目录被占用，启用本地高保真 Neural 语音合成引擎生成配音音频...")
                            if self._synthesize_tts_file(prompt, voice, output_audio_path):
                                return {
                                    "success": True,
                                    "fallback": True,
                                    "text": prompt.strip(),
                                    "audio_url": f"/media/outputs/{output_audio_path.name}",
                                    "audio_path": str(output_audio_path.resolve()),
                                    "image_urls": [],
                                    "profile_id": profile.id,
                                    "profile_name": profile.name,
                                    "warning": f"Profile [{profile.name}] 正在被运行中的 Chrome 窗口占用。已为您自动完成本地配音音频合成。如需 Gemini 分析视频，请先关闭桌面 Chrome 窗口。",
                                    "logs": "\n".join(logs)
                                }
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
                        page.goto("https://gemini.google.com/app", timeout=30000)
                    except Exception as ge:
                        logs.append(f"页面初次加载提醒: {ge}")

                    page.wait_for_timeout(2500)
                    self._dismiss_overlays(page, logs)

                    # 检查输入框与登录态
                    input_selector = 'rich-textarea div[contenteditable="true"], div.ql-editor[contenteditable="true"], [contenteditable="true"], textarea'
                    has_input = False
                    try:
                        page.wait_for_selector(input_selector, timeout=7000)
                        has_input = True
                    except Exception:
                        has_input = False

                    if not has_input:
                        logs.append("未检测到有效输入框，可能未登录或被弹窗拦截")
                        if mode == "dubbing" and prompt and prompt.strip():
                            logs.append("账号未在 Gemini 登录，启用本地高保真 Neural 语音合成引擎生成配音音频...")
                            if self._synthesize_tts_file(prompt, voice, output_audio_path):
                                return {
                                    "success": True,
                                    "fallback": True,
                                    "text": prompt.strip(),
                                    "audio_url": f"/media/outputs/{output_audio_path.name}",
                                    "audio_path": str(output_audio_path.resolve()),
                                    "image_urls": [],
                                    "profile_id": profile.id,
                                    "profile_name": profile.name,
                                    "warning": f"Gemini 网页端未登录 (Profile: {profile.name})，已自动使用广播级音色完成本地配音合成。请点击【🌐 登录网页版】授权 Gemini 进行视频深度分析。",
                                    "logs": "\n".join(logs)
                                }
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
                    media_files = []
                    if has_video:
                        media_files.append(str(Path(video_path).resolve()))
                    if has_image:
                        media_files.append(str(Path(image_path).resolve()))

                    if media_files:
                        file_input = page.query_selector('input[type="file"]')
                        if not file_input:
                            add_btns = page.query_selector_all('button[aria-label*="Upload"], button[aria-label*="Add"], button[mattooltip*="Upload"]')
                            if add_btns:
                                try:
                                    add_btns[0].click()
                                    page.wait_for_timeout(1000)
                                    file_input = page.query_selector('input[type="file"]')
                                except Exception:
                                    pass
                        if file_input:
                            file_input.set_input_files(media_files)
                            logs.append(f"已向 Gemini 输入框附加多模态素材: {[Path(f).name for f in media_files]}")
                            page.wait_for_timeout(3500)

                    # 整理提示词
                    clean_prompt = prompt.strip() if prompt else ""
                    if mode == "dubbing":
                        if not clean_prompt or clean_prompt == "为视频配音":
                            clean_prompt = "请深度分析我提供的视频画面与镜头运镜，生成一段高质量、节奏契合的专业视频宣传解说词。请直接输出配音解说文案，不要有多余寒暄。"
                    elif mode == "image":
                        if not any(k in clean_prompt for k in ["画", "draw", "image", "插画", "图"]):
                            clean_prompt = f"画一张插画：{clean_prompt}"

                    # 填写内容
                    if clean_prompt and input_el:
                        input_el.scroll_into_view_if_needed()
                        input_el.click(force=True)
                        page.wait_for_timeout(300)
                        input_el.fill(clean_prompt)
                        logs.append(f"已输入提示词: {clean_prompt[:60]}...")
                        page.wait_for_timeout(800)

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
                        if s_btn and s_btn.is_visible():
                            s_btn.click(force=True)
                            submitted = True
                            logs.append("已点击发送按钮提交多模态请求")
                            break
                    if not submitted:
                        page.keyboard.press("Enter")
                        logs.append("已通过 Enter 键提交多模态请求")

                    page.wait_for_timeout(3000)

                    # 等待模型回复
                    logs.append("等待 Gemini 响应流...")
                    start_t = time.time()
                    captured_text = ""
                    while (time.time() - start_t) < timeout_sec:
                        time.sleep(2.5)
                        model_responses = page.query_selector_all("model-response")
                        if model_responses:
                            last_resp = model_responses[-1]
                            txt = last_resp.inner_text().strip()
                            if len(txt) > 5:
                                captured_text = txt
                                page.wait_for_timeout(2000)
                                latest_txt = model_responses[-1].inner_text().strip()
                                if latest_txt == captured_text and (time.time() - start_t) > 6:
                                    logs.append("Gemini 回答已完全输出")
                                    break

                    # 检查图片产物 (如果是绘画模式或包含生图)
                    if mode == "image" or any(k in clean_prompt for k in ["画", "生图", "image"]):
                        img_elems = page.query_selector_all("model-response:last-child img, .generated-image img, .image-container img")
                        for idx, im in enumerate(img_elems):
                            src = im.get_attribute("src") or ""
                            if src.startswith("http") or src.startswith("data:") or src.startswith("blob:"):
                                try:
                                    img_save_path = self.output_dir / f"gemini_img_{out_id}_{idx}.png"
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
                                        with open(img_save_path, "wb") as f:
                                            f.write(raw)
                                        output_images.append(f"/media/outputs/{img_save_path.name}")
                                        logs.append(f"成功提取生成的绘画大图: {img_save_path.name}")
                                except Exception as ie:
                                    logs.append(f"提取生成图片异常: {ie}")

                    # 检查音频配音产物 (如果是配音模式或请求了音色)
                    audio_url = None
                    audio_path_str = None
                    if mode == "dubbing" or (voice and mode != "image"):
                        speech_text = captured_text
                        if not speech_text and clean_prompt and mode != "dubbing":
                            speech_text = clean_prompt
                        if "```" in speech_text:
                            parts = speech_text.split("```")
                            speech_text = parts[1] if len(parts) > 1 else speech_text
                        if speech_text.startswith("Gemini said"):
                            speech_text = speech_text[len("Gemini said"):].strip()
                        
                        target_voice = voice if (voice and "Neural" in voice) else "zh-CN-YunxiNeural"
                        logs.append(f"正在为解说词生成高保真 Neural 配音音频 (音色: {target_voice})...")
                        if self._synthesize_tts_file(speech_text, target_voice, output_audio_path):
                            audio_url = f"/media/outputs/{output_audio_path.name}"
                            audio_path_str = str(output_audio_path.resolve())
                            logs.append(f"高品质配音音频生成完成: {output_audio_path.name}")

                    final_text = captured_text or clean_prompt or "（处理完成）"
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
                    browser.close()
                    logs.append("Playwright 浏览器已关闭，系统内存已释放。")

        except Exception as exc:
            logs.append(f"执行 Gemini 多模态交互异常: {exc}")
            # 智能兜底：若是配音需求，绝不让用户扑空
            if mode == "dubbing" and prompt and prompt.strip():
                target_voice = voice if (voice and "Neural" in voice) else "zh-CN-YunxiNeural"
                if self._synthesize_tts_file(prompt, target_voice, output_audio_path):
                    return {
                        "success": True,
                        "fallback": True,
                        "text": prompt.strip(),
                        "audio_url": f"/media/outputs/{output_audio_path.name}",
                        "audio_path": str(output_audio_path.resolve()),
                        "image_urls": [],
                        "profile_id": profile.id,
                        "profile_name": profile.name,
                        "warning": f"Gemini 浏览器交互遇阻 ({exc})，已自动使用广播级 Neural 音色生成配音音频。",
                        "logs": "\n".join(logs)
                    }
            return {
                "success": False,
                "error_code": "EXCEPTION",
                "error_message": str(exc),
                "text": "",
                "audio_url": None,
                "image_urls": [],
                "logs": "\n".join(logs)
            }
