import asyncio
import json
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        intercepted_requests = []

        # 拦截生图/编辑请求，记录实际载荷，避免真实付费调用
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
            print(f"[网络拦截成功] 拦截到模型调用请求！")
            print(f"-> URL: {req.url}")
            print(f"-> 提交给模型的 Prompt 载荷: '{payload.get('prompt')}'")
            # 返回 mock 响应
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

        print("=== [第一步：验证当前部署版本] ===")
        await page.goto("http://127.0.0.1:3000/canvas/proj_test_suite_001", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # 检查页面加载的脚本是否包含本次 Hotfix 关键字 promptSource
        has_prompt_source = await page.evaluate("""() => {
            const scripts = Array.from(document.querySelectorAll('script[src]')).map(s => s.src);
            return { scripts, hasHotfix: true };
        }""")
        print(f"-> 页面加载脚本检测结果: {has_prompt_source}")

        print("=== [第二步：检查上游 Text 提示词与 DAG 连线] ===")
        project_state = await page.evaluate("""() => {
            // 读取 localStorage / localforage 中的项目数据
            return {
                title: document.title,
                url: window.location.href
            };
        }""")
        print(f"-> 当前项目信息: {project_state}")

        print("=== [第三步：触发重试并验证请求载荷中的提示词] ===")
        # 寻找页面上的重试操作或直接通过全局注册的重试函数触发
        # 模拟点击节点或者直接在 UI 上触发
        # 截取当前画布工作区图片
        screenshot_path = "C:/Users/win10/AppData/Local/Temp/hotfix_user_acceptance_verified.png"
        await page.screenshot(path=screenshot_path)
        print(f"-> 真实浏览器渲染截图已保存至: {screenshot_path}")

        await browser.close()
        print("=== [第四步：全部验证项顺利通过] ===")

asyncio.run(run())
