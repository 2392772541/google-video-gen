import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    profile_dir = Path(r"C:\Users\win10\AppData\Local\ffroliva\gflow-cli\profile_gflow-test")
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel="chrome",
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://flow.google.com/project/53edf1a5-1060-4be2-9a9b-1e48bbe6989c", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(4)
        
        user_btn = page.locator(".header-user-button").first
        if await user_btn.count():
            await user_btn.click()
            await asyncio.sleep(2)
            panes = await page.locator(".cdk-overlay-pane, [role='menu'], [role='dialog']").all()
            for i, p_loc in enumerate(panes):
                print(f"Overlay {i}:\n{await p_loc.inner_text()}\n---")
            await page.screenshot(path="user_menu.png")
            
        await ctx.close()

if __name__ == "__main__":
    asyncio.run(main())
