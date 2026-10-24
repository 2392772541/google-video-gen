path = r"C:\Users\win10\Documents\ChatGPT\视频制作\video_farm\gemini_worker.py"
content = open(path, "r", encoding="utf-8").read()

old_block = """                        if len(page.query_selector_all('model-response')) <= baseline_response_count:
                            continue"""

new_block = """                        has_video_indicator = bool(page.query_selector("button[aria-label*='Download video' i], button[aria-label*='下载视频' i], video"))
                        if not has_video_indicator and len(page.query_selector_all('model-response')) <= baseline_response_count:
                            continue"""

assert old_block in content, "old_block not found!"
content = content.replace(old_block, new_block, 1)

old_extract = """                        # C. 检查生成的 video 元素
                        videos = page.query_selector_all('model-response:last-child video')
                        for v in videos:
                            src = v.get_attribute("src")
                            if (src and VidsWorker.media_identity(src) not in baseline_media
                                    and (src.startswith("https://") or src.startswith("blob:"))):
                                logs.append("当前回复内出现新的生成视频，准备本地归档。")
                                logs.append("正在提取完整视频成片...")
                                try:
                                    b64_data = page.evaluate(\"\"\"
                                        async (video) => {
                                            try {
                                                const abort = new AbortController();
                                                const timer = setTimeout(() => abort.abort(), 15000);
                                                let res;
                                                try {res = await fetch(video.src, { credentials: 'include', signal: abort.signal });}
                                                finally {clearTimeout(timer);}
                                                if (!res.ok) return null;
                                                const blob = await res.blob();
                                                if (blob.size > 64*1024*1024) throw Error('video exceeds 64MiB');
                                                return new Promise((resolve) => {
                                                    const reader = new FileReader();
                                                    reader.onloadend = () => resolve(reader.result);
                                                    reader.readAsDataURL(blob);
                                                });
                                            } catch (err) {
                                                return null;
                                            }
                                        }
                                    \"\"\", v)
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
                                except ExecutionStopped:
                                    raise
                                except Exception as e_ev:
                                    logs.append(f"页面内视频流提取提示: {e_ev}")

                        # D. 兜底方案：通过页面原生下载按钮
                        if not video_found:
                            dl_btns = page.query_selector_all("model-response:last-child a[download], model-response:last-child button[aria-label*='Download video'], model-response:last-child button[aria-label*='下载视频']")
                            if dl_btns and len(dl_btns) > 0:
                                dl_btn = dl_btns[-1]
                                if dl_btn.is_visible():
                                    try:
                                        logs.append("检测到成片下载按钮，尝试直接触发原生文件下载...")
                                        with page.expect_download(timeout=self._timeout(8000)) as dl_info:
                                            dl_btn.click(timeout=self._timeout())
                                        download = dl_info.value
                                        download.save_as(str(output_video_path))
                                        if output_video_path.exists() and output_video_path.stat().st_size > 20000:
                                            logs.append(f"已成功通过下载通道获取成片 ({output_video_path.stat().st_size} 字节)")
                                            video_found = True
                                            break
                                    except ExecutionStopped:
                                        raise
                                    except Exception as de:
                                        logs.append(f"原生下载尝试提示: {de}")"""

new_extract = """                        # C. 优先通过页面原生下载按钮获取成片（最稳定、最保真、包含全部音频与元数据）
                        responses = page.query_selector_all("model-response")
                        last_resp = responses[-1] if responses else None

                        dl_selectors = [
                            "button[aria-label*='Download video' i]",
                            "button[aria-label*='下载视频' i]",
                            "button[aria-label*='下载' i]",
                            "a[download]",
                            "a[href*='download']"
                        ]
                        candidate_dl_btns = []
                        if last_resp:
                            for ds in dl_selectors:
                                candidate_dl_btns.extend(last_resp.query_selector_all(ds))
                        if not candidate_dl_btns:
                            for ds in dl_selectors:
                                candidate_dl_btns.extend(page.query_selector_all(ds))

                        for dl_btn in candidate_dl_btns:
                            if dl_btn and dl_btn.is_visible():
                                try:
                                    logs.append("检测到成片下载按钮，尝试直接触发原生文件下载...")
                                    with page.expect_download(timeout=self._timeout(15000)) as dl_info:
                                        dl_btn.click(timeout=self._timeout(5000))
                                    download = dl_info.value
                                    download.save_as(str(output_video_path))
                                    if output_video_path.exists() and output_video_path.stat().st_size > 20000:
                                        logs.append(f"已成功通过下载通道获取成片 ({output_video_path.stat().st_size} 字节): {output_video_path}")
                                        video_found = True
                                        break
                                except ExecutionStopped:
                                    raise
                                except Exception as de:
                                    logs.append(f"原生下载尝试提示: {de}")

                        # D. 兜底方案：通过页面安全上下文提取视频流
                        if not video_found:
                            candidate_videos = last_resp.query_selector_all("video") if last_resp else []
                            if not candidate_videos:
                                candidate_videos = page.query_selector_all("video")

                            for v in candidate_videos:
                                src = v.get_attribute("src") or page.evaluate("el => el.currentSrc || el.src", v)
                                if (src and VidsWorker.media_identity(src) not in baseline_media
                                        and (src.startswith("https://") or src.startswith("blob:"))):
                                    logs.append("当前回复内出现新的生成视频，准备本地归档。")
                                    logs.append("正在提取完整视频成片...")
                                    try:
                                        b64_data = page.evaluate(\"\"\"
                                            async (video) => {
                                                try {
                                                    const abort = new AbortController();
                                                    const timer = setTimeout(() => abort.abort(), 20000);
                                                    let res;
                                                    const targetSrc = video.currentSrc || video.src || video.querySelector('source')?.src;
                                                    if (!targetSrc) return null;
                                                    try { res = await fetch(targetSrc, { credentials: 'include', signal: abort.signal }); }
                                                    finally { clearTimeout(timer); }
                                                    if (!res.ok) return null;
                                                    const blob = await res.blob();
                                                    if (blob.size > 128*1024*1024) throw Error('video exceeds 128MiB');
                                                    return new Promise((resolve) => {
                                                        const reader = new FileReader();
                                                        reader.onloadend = () => resolve(reader.result);
                                                        reader.readAsDataURL(blob);
                                                    });
                                                } catch (err) {
                                                    return null;
                                                }
                                            }
                                        \"\"\", v)
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
                                    except ExecutionStopped:
                                        raise
                                    except Exception as e_ev:
                                        logs.append(f"页面内视频流提取提示: {e_ev}")"""

assert old_extract in content, "old_extract not found!"
content = content.replace(old_extract, new_extract, 1)

open(path, "w", encoding="utf-8").write(content)
print("gemini_worker.py successfully patched!")
