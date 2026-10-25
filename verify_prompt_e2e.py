import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        print("[1] 进入画布项目...")
        await page.goto("http://127.0.0.1:3000/canvas/proj_test_suite_001", wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # 点击画布中的图片节点（直接点击 img 标签或节点卡片）
        print("[2] 点击画布中央的图片节点...")
        img_elem = page.locator('img[src*="data:image"], img[alt]').first
        if await img_elem.count() > 0:
            await img_elem.click()
            await page.wait_for_timeout(1000)
            print("-> 已点击图片节点")

        # 检查是否唤起了底部操作面板
        print("[3] 查找底部 PromptPanel 与 role='textbox' 输入框...")
        panel = page.locator('[data-canvas-no-zoom]').first
        if await panel.count() > 0:
            print("-> 成功唤起底部操作面板！")
            editor = page.locator('div[role="textbox"]').first
            if await editor.count() > 0:
                val = await editor.text_content()
                print(f"-> 底部面板输入框自动提取并回显的提示词: '{val}'")

            screenshot_path = "C:/Users/win10/AppData/Local/Temp/panel_prompt_verified_final.png"
            await page.screenshot(path=screenshot_path)
            print(f"-> 最终现场验证截图已保存至: {screenshot_path}")

        await browser.close()
        print("=== 验证流程完成 ===")

asyncio.run(run())
