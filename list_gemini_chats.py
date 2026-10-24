from pathlib import Path
from playwright.sync_api import sync_playwright

profile_dir = Path(r"C:\Users\win10\AppData\Local\ffroliva\gflow-cli\profile_gflow-test")
with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(user_data_dir=str(profile_dir), channel="chrome", headless=True)
    page = browser.new_page()
    page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=25000)
    page.wait_for_timeout(3000)
    links = page.query_selector_all("a")
    for a in links:
        href = a.get_attribute("href") or ""
        txt = a.inner_text().strip().replace("\n", " ")
        if "/app/" in href or "视频" in txt or "生成" in txt:
            print(f"Chat: href='{href}', text='{txt}'")
    browser.close()
