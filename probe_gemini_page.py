import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

def probe():
    profile_dir = Path(r"C:\Users\win10\AppData\Local\ffroliva\gflow-cli\profile_gflow-test")
    print(f"Probing Gemini with profile: {profile_dir}")
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel="chrome",
            headless=True,
            args=["--disable-infobars"]
        )
        page = browser.new_page()
        page.set_default_timeout(15000)
        try:
            print("Navigating to https://gemini.google.com/app ...")
            page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)
            print("URL:", page.url)
            print("Title:", page.title())
            page.screenshot(path="probe_gemini_app.png")
            print("Screenshot saved to probe_gemini_app.png")

            # Check if logged in
            text = page.locator("body").inner_text()
            print("Has login / Sign in:", "Sign in" in text or "登录" in text)
            print("Has textarea / input:", page.locator("rich-textarea, textarea, [contenteditable='true']").count())

            # Try /videos
            print("Navigating to https://gemini.google.com/videos ...")
            page.goto("https://gemini.google.com/videos", wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(3000)
            print("Videos URL:", page.url)
            print("Videos Title:", page.title())
            page.screenshot(path="probe_gemini_videos.png")
            print("Videos screenshot saved to probe_gemini_videos.png")
            vtext = page.locator("body").inner_text()
            print("Videos page body snippet:", repr(vtext[:300]))
        except Exception as e:
            print("Probe error:", e)
        finally:
            browser.close()

if __name__ == "__main__":
    probe()
