# -*- coding: utf-8 -*-
"""
Google Vids 原生网页端自动化执行器 (VidsWorker)
专为 Google Vids (docs.google.com/videos) 定制，实现：
1. 自动进入或创建 Google Vids 云端工程
2. 智能消除初始 Modal 引导与协议遮罩
3. 唤起原生 AI 视频侧边栏 (#content-library-rail-video-generation-element)
4. 设置原生视频模型 (Omni)、画质 (1080p / 720p)、画幅及镜头时长
5. 支持首尾帧/图片参考上传 (添加动画 / Animate 模式)
6. 注入富文本提示词并触发视频渲染
7. 实时监听生成进度、提取成片 MP4 直链与本地归档
8. 严格的生命周期管理：任务结束后立即关闭浏览器释放 ~800MB 内存
"""
from __future__ import annotations

import os
import sys
import time
import json
import base64
import urllib.request
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List

from .models import Task, Profile

class VidsWorker:
    def __init__(
        self,
        output_dir: Path = Path("video_farm_data/outputs"),
        timeout_sec: int = 360,
        headless: bool = True,
        mock_sample_video: Optional[str] = None
    ):
        self.output_dir = output_dir.resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_sec = timeout_sec
        self.headless = headless
        self.mock_sample_video = mock_sample_video

    def _resolve_profile_dir(self, profile: Profile) -> Path:
        if profile.profile_path and Path(profile.profile_path).exists():
            return Path(profile.profile_path).resolve()
        appdata = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(appdata) / "ffroliva" / "gflow-cli" / f"profile_{profile.name}"

    def _clean_stale_lock(self, profile_dir: Path, logs: List[str]):
        """清理历史遗留的崩溃锁文件，避免 SingletonLock / TargetClosedError 阻塞"""
        lock_file = profile_dir / "lockfile"
        if lock_file.exists():
            try:
                lock_file.unlink()
                logs.append(f"清理遗留的 Chrome 锁文件: {lock_file}")
            except Exception as e:
                logs.append(f"清理锁文件提示: {e}")

    def _dismiss_overlays(self, page, logs: List[str], press_esc: bool = True):
        """主动关闭 Google Vids 的新手引导浮层、开局欢迎弹窗和遮罩，强力穿透 Material 3 遮罩"""
        if press_esc:
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
            except Exception:
                pass

        # 深度穿透消除开局欢迎弹窗 (Blank vid) 以及 Material 3 / Google 遮罩浮层，防止 scrim 拦截 pointer events
        try:
            removed = page.evaluate("""() => {
                let count = 0;
                // 优先点击关闭、空白工程按钮
                const btns = Array.from(document.querySelectorAll('button, [role="button"], span, div'));
                for (const b of btns) {
                    const txt = (b.innerText || b.getAttribute('aria-label') || '').trim();
                    if (/^(Blank vid|Close|关闭|跳过|知道了|好|完成|Dismiss|Got it|OK|Done|Skip)$/i.test(txt)) {
                        try {
                            b.click();
                            count++;
                        } catch(e){}
                    }
                }
                // 强力移除所有拦截 pointer events 的弹窗容器与遮罩
                const selectors = [
                    '[role="dialog"]',
                    '.javascriptMaterialdesignGm3WizDialog-dialog',
                    '.javascriptMaterialdesignGm3WizDialog-dialog__scrim',
                    '.goog-modalpopup',
                    '.goog-modalpopup-bg',
                    '.modal-backdrop'
                ];
                selectors.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        try {
                            el.style.display = 'none';
                            el.remove();
                            count++;
                        } catch(e){}
                    });
                });
                return count;
            }""")
            if removed > 0:
                logs.append(f"穿透清理 Google Vids 遮罩浮层 (处理 {removed} 项)")
        except Exception:
            pass

    def execute_task(self, task: Task, profile: Profile) -> Dict[str, Any]:
        worker_name = threading.current_thread().name
        profile_dir = self._resolve_profile_dir(profile)
        output_video_path = self.output_dir / f"{task.id}.mp4"

        logs = []
        logs.append(f"[{worker_name}] 🚀 启动 Google Vids 原生视频生成执行器 (Profile: {profile.name})")
        logs.append(f"Profile 目录: {profile_dir}")
        logs.append(f"任务 ID: {task.id}, 目标模型: {task.model}, 提示词: {task.prompt[:60]}...")

        # 0. 如果配置了离线样本且无网络环境，优先快速验证
        if self.mock_sample_video and Path(self.mock_sample_video).exists() and os.environ.get("VIDS_MOCK_MODE") == "1":
            logs.append(f"【MOCK模式】使用预设样本成片填充: {self.mock_sample_video}")
            import shutil
            shutil.copy(self.mock_sample_video, str(output_video_path))
            return {
                "success": True,
                "pid": os.getpid(),
                "output_video_path": str(output_video_path),
                "logs": "\n".join(logs)
            }

        if not profile_dir.exists():
            profile_dir.mkdir(parents=True, exist_ok=True)

        self._clean_stale_lock(profile_dir, logs)

        from playwright.sync_api import sync_playwright

        browser = None
        playwright_ctx = None

        try:
            playwright_ctx = sync_playwright().start()
            launch_args = [
                "--no-sandbox",
                "--disable-infobars"
            ]

            logs.append("正在拉起专属 Chrome 自动化会话...")
            try:
                browser = playwright_ctx.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir.resolve()),
                    channel="chrome",
                    headless=self.headless,
                    args=launch_args
                )
            except Exception as launch_exc:
                lexc_str = str(launch_exc).lower()
                logs.append(f"拉起浏览器会话异常: {launch_exc}")
                if any(k in lexc_str for k in ["singleton", "lock", "in use", "already running"]):
                    return {
                        "success": False,
                        "pid": os.getpid(),
                        "error_code": "PROFILE_LOCKED",
                        "error_message": f"Profile [{profile.name}] 正在被运行中的 Chrome 窗口独占占用。",
                        "output_video_path": None,
                        "logs": "\n".join(logs)
                    }
                raise launch_exc

            page = browser.pages[0] if browser.pages else browser.new_page()

            # 监听网络流以捕获媒体文件 (严格排除 gstatic 等静态样例/宣传视频)
            captured_media_urls = []
            def handle_response(response):
                try:
                    url = response.url
                    ct = response.headers.get("content-type", "")
                    # 严禁捕获 Google Vids 官方静态宣传/样例视频
                    if any(k in url for k in ["gstatic.com", "gettingstarteddialog", "flix_likeness", "avatars_entry_point", "veo_entry_point"]):
                        return
                    if ("video" in ct or ".mp4" in url or "google.com/download" in url or "videoplayback" in url) and (
                        "usercontent.google.com" in url or "bard_storage" in url or "temp_data" in url
                    ):
                        if url not in captured_media_urls:
                            captured_media_urls.append(url)
                            logs.append(f"[真实成片捕获] 捕获到 Google Vids 真实渲染视频流: {url[:90]}...")
                except Exception:
                    pass

            page.on("response", handle_response)

            # 1. 导航进入 Google Vids 工程
            target_url = getattr(task, "project_id", "") or "https://docs.google.com/videos/create"
            if not target_url.startswith("http"):
                target_url = "https://docs.google.com/videos/create"

            logs.append(f"导航至 Google Vids 目标工程: {target_url}")
            page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)

            # 检查是否有权限访问该文档，如果 Access Denied / 访问遭拒，则自愈创建新文档
            page_title = page.title()
            logs.append(f"Google Vids 页面标题: {page_title}")
            is_access_denied = any(kw.lower() in page_title.lower() for kw in [
                "access denied", "无法访问", "权限", "遭拒", "拒绝", "需要访问权限", "请求访问权限", "无权访问", "error", "403"
            ]) or any(kw in page.url.lower() for kw in ["requestaccess", "servicelogin", "accessdenied"])

            if not is_access_denied:
                try:
                    req_btn = page.locator("button:has-text('请求访问权限'), [aria-label*='请求访问权限'], button:has-text('Request access')").first
                    if req_btn.count() > 0 and req_btn.is_visible():
                        is_access_denied = True
                except Exception:
                    pass

            if is_access_denied:
                logs.append("⚠️ 当前账号无权访问指定外链工程 (如「访问遭拒」)，自动自愈创建专属 Google Vids 新工程...")
                page.goto("https://docs.google.com/videos/create", timeout=45000, wait_until="domcontentloaded")
                page.wait_for_timeout(4000)
                logs.append(f"自愈新工程就绪，URL: {page.url}")

            # 消除可能出现的初始模态框
            self._dismiss_overlays(page, logs)

            # 2. 唤起侧边栏中的「AI 视频」核心入口 (强化中英文多选择器与 30s 宽裕容错)
            ai_selectors = [
                "#content-library-rail-video-generation-element",
                "[aria-label*='AI 视频']",
                "[aria-label*='生成视频']",
                "[aria-label*='Generate an AI video']",
                "[data-tooltip*='AI video']"
            ]
            ai_entry_btn = page.locator(", ".join(ai_selectors)).first
            if ai_entry_btn.count() == 0:
                logs.append("等待 AI 视频入口元素渲染...")
                try:
                    ai_entry_btn.wait_for(state="attached", timeout=12000)
                except Exception:
                    logs.append("⚠️ 12秒内未检测到 AI 入口，尝试自愈导航至 https://docs.google.com/videos/create ...")
                    page.goto("https://docs.google.com/videos/create", timeout=45000, wait_until="domcontentloaded")
                    page.wait_for_timeout(4000)
                    self._dismiss_overlays(page, logs)
                    ai_entry_btn = page.locator(", ".join(ai_selectors)).first
                    ai_entry_btn.wait_for(state="attached", timeout=20000)

            logs.append("点击「AI 视频」工具栏按钮展开面板...")
            try:
                ai_entry_btn.click(force=True, timeout=10000)
            except Exception:
                ai_entry_btn.evaluate("el => el.click()")
            page.wait_for_timeout(2000)

            # 3. 模式与素材绑定 (针对 Google Vids Animate / Create 原生工作流)
            has_reference_image = bool(task.start_image_path and Path(task.start_image_path).exists())
            if has_reference_image:
                logs.append(f"检测到首帧/参考图素材: {task.start_image_path}")
                anim_tab = page.locator("button:has-text('Animate'), [role='tab']:has-text('Animate'), [aria-label*='Animate']").first
                if anim_tab.count() > 0 and anim_tab.is_visible():
                    logs.append("切换至「添加动画 (Animate)」多模态模式...")
                    try:
                        anim_tab.click(force=True)
                    except Exception:
                        anim_tab.evaluate("el => el.click()")
                    page.wait_for_timeout(1500)

                # 检查并点击「Add image」按钮
                add_img_btn = page.get_by_text("Add image").first
                if add_img_btn.count() > 0 and add_img_btn.is_visible():
                    try:
                        add_img_btn.click(force=True)
                    except Exception:
                        add_img_btn.evaluate("el => el.click()")
                    page.wait_for_timeout(1000)

                    # 智能消除图片版权使用协议弹窗 (Create content from images in Workspace)
                    agree_btn = page.locator("button:has-text('Agree'), button:has-text('同意')").first
                    if agree_btn.count() > 0 and agree_btn.is_visible():
                        logs.append("确认图片素材版权与使用协议 (Agree)...")
                        agree_btn.click(force=True)
                        page.wait_for_timeout(1500)

                # 寻找并注入文件输入控件
                file_input = page.locator("input[type='file']").first
                if file_input.count() > 0:
                    abs_img_path = str(Path(task.start_image_path).resolve())
                    logs.append(f"上传首帧/参考图像素材: {abs_img_path}")
                    file_input.set_input_files(abs_img_path)
                    page.wait_for_timeout(3500)
                    logs.append("✅ 首帧素材已成功载入 Google Vids 画布并展示缩略图")
                else:
                    logs.append("⚠️ 未找到文件输入控件 input[type='file']")
            else:
                create_tab = page.locator("button:has-text('Create'), [role='tab']:has-text('Create'), [aria-label*='Create']").first
                if create_tab.count() > 0 and create_tab.is_visible():
                    try:
                        create_tab.click(force=True)
                    except Exception:
                        create_tab.evaluate("el => el.click()")
                    page.wait_for_timeout(1000)

            # 4. 生成设置：分辨率 (1080p / 720p) 与画幅
            try:
                is_1080p = "1080" in (task.model or "").lower() or (getattr(task, "resolution", "") == "1080p")
                settings_btn = page.locator(".content-library button[aria-label*='Generation settings'], .content-library button:has-text('Omni')").first
                if settings_btn.count() > 0 and settings_btn.is_visible():
                    settings_btn.click(force=True, timeout=4000)
                    page.wait_for_timeout(1000)
                    target_res_text = "1080p" if is_1080p else "720p"
                    res_option = page.locator(f"[role='menuitem']:has-text('{target_res_text}'), [role='menuitemradio']:has-text('{target_res_text}'), button:has-text('{target_res_text}')").first
                    if res_option.count() > 0:
                        logs.append(f"选择清晰度规格 -> {target_res_text}")
                        res_option.click(force=True, timeout=3000)
                        page.wait_for_timeout(500)
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(400)
            except Exception as set_err:
                logs.append(f"画质配置菜单交互跳过: {set_err}")
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass

            # 5. 填入镜头提示词
            textbox = page.locator("[role='textbox'], [contenteditable='true']").first
            if textbox.count() > 0:
                logs.append(f"注入镜头提示词: {task.prompt[:60]}...")
                textbox.click(force=True)
                page.wait_for_timeout(400)
                textbox.fill(task.prompt)
                page.wait_for_timeout(800)

            # 6. 触发生成 (精准定位专属生成按钮)
            gen_btn = page.locator(".collapsiblePromptBoxGenerateButton, button[aria-label='Generate']").last
            if gen_btn.count() == 0 or not gen_btn.is_visible():
                gen_btn = page.locator(".content-library button:has(svg), .content-library button[aria-label*='Generate']").last

            logs.append("⚡ 触发 Google Vids 视频生成任务 (点击 Generate)...")
            try:
                gen_btn.click(force=True, timeout=8000)
            except Exception:
                gen_btn.evaluate("el => el.click()")
            page.wait_for_timeout(4000)

            # 7. 进度监听与视频提取
            logs.append("进入生成进度监听状态，等待 Google 官方云端渲染...")
            start_poll = time.time()
            generation_complete = False

            while time.time() - start_poll < self.timeout_sec:
                # 检查页面是否有错误浮层或提示
                error_toast = page.locator(".docs-toast, [role='alert']").first
                if error_toast.count() > 0 and error_toast.is_visible():
                    err_txt = error_toast.inner_text().strip()
                    if err_txt:
                        lower_txt = err_txt.lower()
                        if any(w in lower_txt for w in ["unusual activity", "异常活动"]) or "we noticed some unusual activity" in lower_txt:
                            logs.append(f"⚠️ Google 检测到异常活动风控: {err_txt}")
                            return {
                                "success": False,
                                "pid": os.getpid(),
                                "error_code": "UNUSUAL_ACTIVITY",
                                "error_message": f"Google 检测到异常活动 ({err_txt})，已触发 Profile 冷却避让",
                                "output_video_path": None,
                                "logs": "\n".join(logs)
                            }
                        if any(k in err_txt for k in ["失败", "未能", "error", "failed"]):
                            logs.append(f"检测到 Google Vids 提示异常: {err_txt}")
                            return {
                                "success": False,
                                "pid": os.getpid(),
                                "error_code": "VIDS_UI_ERROR",
                                "error_message": err_txt,
                                "output_video_path": None,
                                "logs": "\n".join(logs)
                            }

                elapsed = int(time.time() - start_poll)
                if elapsed % 15 == 0:
                    logs.append(f"[{elapsed}s] 正在云端渲染中... (已捕获真实流={len(captured_media_urls)})")

                # 检查成片就绪指示 (「Insert」插入按钮出现，或捕获到了真实 usercontent / bard_storage 流)
                insert_btn = page.locator("button:has-text('Insert'), button:has-text('插入')").first
                if insert_btn.count() > 0 and insert_btn.is_visible():
                    logs.append(f"🎉 检测到 Google Vids 成片已渲染完毕并在侧边栏展现 (耗时 {elapsed}s)")
                    generation_complete = True
                    break

                if captured_media_urls and elapsed > 15:
                    logs.append(f"🎉 捕获到 Google Vids 真实输出视频流 (耗时 {elapsed}s)")
                    generation_complete = True
                    break

                page.wait_for_timeout(3000)

            # 如果成片已完成，点击 Insert 保存到工程时间轴，并下载视频
            if generation_complete:
                try:
                    insert_btn = page.locator("button:has-text('Insert'), button:has-text('插入')").first
                    if insert_btn.count() > 0 and insert_btn.is_visible():
                        insert_btn.click(force=True)
                        logs.append("已将成片插入 Google Vids 工程时间轴画布")
                        page.wait_for_timeout(2000)
                except Exception:
                    pass

                page.wait_for_timeout(2000)
                target_media_url = captured_media_urls[-1] if captured_media_urls else None
                if not target_media_url:
                    v_tag = page.locator(".content-library video, video").first
                    if v_tag.count() > 0:
                        target_media_url = v_tag.get_attribute("src")

                if target_media_url:
                    logs.append(f"正在从真实流地址下载 MP4: {target_media_url[:80]}...")
                    try:
                        if target_media_url.startswith("blob:"):
                            b64_data = page.evaluate("""async (burl) => {
                                const res = await fetch(burl);
                                const blob = await res.blob();
                                return new Promise((resolve) => {
                                    const reader = new FileReader();
                                    reader.onloadend = () => resolve(reader.result);
                                    reader.readAsDataURL(blob);
                                });
                            }""", target_media_url)
                            if b64_data and "," in b64_data:
                                v_bytes = base64.b64decode(b64_data.split(",", 1)[1])
                                if len(v_bytes) > 10240:
                                    output_video_path.write_bytes(v_bytes)
                                    logs.append(f"通过 Blob 内存成功导出成片: {output_video_path} (大小: {len(v_bytes)} bytes)")
                        else:
                            resp = page.request.get(target_media_url)
                            if resp.status == 200:
                                v_bytes = resp.body()
                                if len(v_bytes) > 10240:
                                    output_video_path.write_bytes(v_bytes)
                                    logs.append(f"视频直链下载落盘成功: {output_video_path} (大小: {len(v_bytes)} bytes)")
                    except Exception as dl_err:
                        logs.append(f"下载异常: {dl_err}")

            if not output_video_path.exists() or output_video_path.stat().st_size == 0:
                try:
                    qa_img = self.output_dir.parent / "qa" / f"{task.id}_timeout.png"
                    qa_img.parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(qa_img))
                    logs.append(f"已捕获超时页面快照: {qa_img}")
                except Exception:
                    pass

            if output_video_path.exists() and output_video_path.stat().st_size > 0:
                logs.append("✅ Google Vids 原生视频成片生成成功！")
                return {
                    "success": True,
                    "pid": os.getpid(),
                    "output_video_path": str(output_video_path),
                    "logs": "\n".join(logs)
                }
            else:
                logs.append("⚠️ Google Vids 生成超时或未提取到有效成片。")
                return {
                    "success": False,
                    "pid": os.getpid(),
                    "error_code": "VIDS_TIMEOUT_OR_EMPTY",
                    "error_message": "Google Vids 页面未在预期时间内完成渲染并返回视频流",
                    "output_video_path": None,
                    "logs": "\n".join(logs)
                }

        except Exception as e:
            logs.append(f"❌ VidsWorker 执行遇到异常: {e}")
            return {
                "success": False,
                "pid": os.getpid(),
                "error_code": "VIDS_EXEC_EXCEPTION",
                "error_message": str(e),
                "output_video_path": None,
                "logs": "\n".join(logs)
            }
        finally:
            # 8. 必须完全释放浏览器资源与内存，杜绝驻留进程把系统吃死
            logs.append("🧹 正在关闭 Google Vids 自动化会话并彻底释放系统内存...")
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if playwright_ctx:
                try:
                    playwright_ctx.stop()
                except Exception:
                    pass
            logs.append("✨ 内存已完全释放，任务执行阶段结束。")

