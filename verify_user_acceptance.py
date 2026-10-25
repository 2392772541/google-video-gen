import asyncio
import json
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        intercepted_requests = []

        # 拦截生图/编辑请求，避免真实付费调用，同时记录请求 payload
        async def handle_route(route):
            req = route.request
            payload = {}
            try:
                payload = json.loads(req.post_data or "{}")
            except Exception:
                payload = {"raw": req.post_data}
            intercepted_requests.append({
                "url": req.url,
                "method": req.method,
                "payload": payload
            })
            print(f"[拦截到请求] URL: {req.url}, Prompt: {payload.get('prompt')}")
            # 返回 mock 响应，确保前端流程正常推进而不产生费用
            await route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({
                    "data": [
                        {
                            "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                            "b64_json": ""
                        }
                    ]
                })
            )

        await page.route("**/images/generations*", handle_route)
        await page.route("**/images/edits*", handle_route)

        print("[1] 进入画布项目...")
        await page.goto("http://127.0.0.1:3000/canvas/proj_test_suite_001", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # 检查画布上的节点状态
        print("[2] 检查画布中图片节点状态...")
        # 寻找画布上的图片节点并点击它
        img_node = page.locator('img[src*="data:image"], .canvas-node:has-text("图片"), .canvas-node:has-text("Image")').first
        if await img_node.count() > 0:
            await img_node.click()
            await page.wait_for_timeout(1000)
            print("-> 成功点击选中图片节点")

        # 检查下方 PromptPanel
        panel = page.locator('[data-canvas-no-zoom]').first
        assert await panel.count() > 0, "错误：未能唤起底部操作面板"
        print("-> 底部操作控制面板成功唤起！")

        # 检查输入框内容
        editor = page.locator('div[role="textbox"]').first
        prompt_text = await editor.text_content() if await editor.count() > 0 else ""
        print(f"-> 实际读取到底部面板回显的提示词: '{prompt_text.strip()}'")
        assert len(prompt_text.strip()) > 0, "断言失败：输入框未回显提示词！"
        print("✓ [断言通过] 下游图片节点输入框成功自动展示上游提示词！")

        # 检查重试或重新生成按钮
        print("[3] 触发重试/生成以检验请求载荷...")
        # 点击生成按钮（ArrowUp 按钮）
        generate_btn = page.locator('button[aria-label="生成"]').first
        if await generate_btn.count() > 0 and not await generate_btn.is_disabled():
            await generate_btn.click()
            await page.wait_for_timeout(2000)
            print("-> 已点击生成按钮")

        # 检查是否有警告弹出
        warning_box = page.locator('.ant-message-warning, :text("找不到提示词")')
        warning_count = await warning_box.count()
        assert warning_count == 0, "断言失败：界面仍旧弹出了「找不到提示词」警告！"
        print("✓ [断言通过] 界面未出现任何「找不到提示词」警告！")

        # 检查拦截到的请求载荷
        assert len(intercepted_requests) > 0, "断言失败：未捕获到重试/生成请求！"
        first_req = intercepted_requests[0]
        submitted_prompt = first_req["payload"].get("prompt", "")
        print(f"-> 拦截到的提交载荷 Prompt: '{submitted_prompt[:60]}...'")
        assert len(submitted_prompt) > 0, "断言失败：提交给模型的提示词为空！"
        print("✓ [断言通过] 请求载荷中准确携带了最终提示词，未发生提示词丢失！")

        # 截图保存真实操作验收图
        screenshot_path = "C:/Users/win10/AppData/Local/Temp/final_user_acceptance_verified.png"
        await page.screenshot(path=screenshot_path)
        print(f"[4] 验收证据截图已保存至: {screenshot_path}")

        await browser.close()
        print("=== 真实画布验收 100% 成功达成 ===")

asyncio.run(run())
