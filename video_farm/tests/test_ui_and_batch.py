# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright
import time
import json
import zipfile
import io
import requests

def run_tests():
    print("=== 开始执行自动化测试 ===")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        
        print("[1] 访问 http://127.0.0.1:8088/ ...")
        page.goto("http://127.0.0.1:8088/", wait_until="networkidle")
        print("页面标题:", page.title())
        
        # 1. 检查默认 tab
        active_tab = page.query_selector(".tab-button.active")
        print("默认活跃 Tab:", active_tab.inner_text().strip() if active_tab else "无")
        
        # 2. 点击切换到【任务与成片】标签页
        tasks_tab = page.query_selector('.tab-button[data-target="view-tasks"]')
        assert tasks_tab is not None, "未找到任务与成片 Tab"
        print("点击切换到【任务与成片】Tab...")
        tasks_tab.click()
        page.wait_for_timeout(1500)
        
        # 3. 检查 view-tasks 可见性
        view_tasks = page.query_selector("#view-tasks")
        assert view_tasks and view_tasks.is_visible(), "#view-tasks 视图未显示"
        print("#view-tasks 视图正常可见: True")
        
        # 4. 检查批量操作栏及所有相关按钮的可见性与位置
        selectors = {
            "batch_action_bar": "#batch-action-bar",
            "select_all_chk": "#batch-select-all-chk",
            "btn_invert": "#btn-batch-invert",
            "btn_clear": "#btn-batch-clear",
            "btn_batch_select_completed": "#btn-batch-select-completed",
            "btn_quick_select_completed": "#btn-quick-select-completed",
            "batch_stats_text": "#batch-stats-text",
            "btn_download": "#btn-batch-download",
            "btn_delete": "#btn-batch-delete"
        }
        
        visibility_report = {}
        for name, sel in selectors.items():
            el = page.query_selector(sel)
            if not el:
                visibility_report[name] = {"found": False, "visible": False, "box": None}
            else:
                vis = el.is_visible()
                box = el.bounding_box()
                visibility_report[name] = {"found": True, "visible": vis, "box": box}
            print(f" - {name} ({sel}): {visibility_report[name]}")
            
        page.screenshot(path="video_farm/tests/screenshot_tasks_tab.png")
        print("已截取任务与成片页初始截图: video_farm/tests/screenshot_tasks_tab.png")
        
        # 5. 交互测试：点击【一键勾选所有已完成成片】
        btn_quick = page.query_selector("#btn-quick-select-completed")
        print("点击顶部【✨ 勾选所有成片】按钮...")
        btn_quick.click()
        page.wait_for_timeout(1000)
        
        # 统计选中的卡片
        checked_boxes = page.query_selector_all(".task-select-chk:checked")
        print(f"已勾选卡片复选框数量: {len(checked_boxes)}")
        
        stats_text = page.query_selector("#batch-stats-text").inner_text()
        print(f"底部状态栏文本: {stats_text}")
        
        btn_dl = page.query_selector("#btn-batch-download")
        dl_disabled = btn_dl.is_disabled()
        dl_text = btn_dl.inner_text()
        print(f'下载按钮状态: disabled={dl_disabled}, text="{dl_text}"')
        assert not dl_disabled, "有选中成片时下载按钮应处于启用状态"
        
        page.screenshot(path="video_farm/tests/screenshot_after_quick_select.png")
        print("已截取勾选成片后的截图: video_farm/tests/screenshot_after_quick_select.png")
        
        # 6. 测试全选复选框
        btn_clear = page.query_selector("#btn-batch-clear")
        print("点击清空勾选...")
        btn_clear.click()
        page.wait_for_timeout(500)
        stats_after_clear = page.query_selector("#batch-stats-text").inner_text()
        print(f"清空后状态栏文本: {stats_after_clear}")
        
        chk_all = page.query_selector("#batch-select-all-chk")
        print("点击【全选本页】复选框...")
        chk_all.check()
        page.wait_for_timeout(800)
        checked_after_all = page.query_selector_all(".task-select-chk:checked")
        print(f"全选后勾选数量: {len(checked_after_all)}")
        
        # 7. 测试反选
        btn_invert = page.query_selector("#btn-batch-invert")
        print("点击【反选】按钮...")
        btn_invert.click()
        page.wait_for_timeout(800)
        checked_after_invert = page.query_selector_all(".task-select-chk:checked")
        print(f"反选后勾选数量: {len(checked_after_invert)}")
        
        browser.close()
        print("=== UI与交互测试完成 ===")

if __name__ == "__main__":
    run_tests()
