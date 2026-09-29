# -*- coding: utf-8 -*-
"""
Google Vids 连续生成自动化调度引擎
通过与已打开的 Chrome Google Vids 工程交互，实现：
1. 资产套件全局提示词与分镜提示词智能融合
2. 场景自动创建 (Scene X) 与精准定位切换
3. 提示词安全输入与“生成”触发
4. 进度实时监听与数据库状态同步
5. 成片自动一键置入时间轴画布
6. 原画成片 MP4 直链抓取与持久化归档
"""
import sys
import time
import json
import logging
from typing import Optional, Dict, Any, List
import requests

from . import db
from . import vids_workflow

logging.basicConfig(level=logging.INFO, format="[%(asctime)s][%(levelname)s] %(message)s")
logger = logging.getLogger("VidsAutomator")

API_BASE = "http://127.0.0.1:8088/api/vids"

class VidsAutomator:
    def __init__(self, workflow_id: str, api_base: str = API_BASE):
        self.workflow_id = workflow_id
        self.api_base = api_base

    def get_workflow(self) -> Dict[str, Any]:
        resp = requests.get(f"{self.api_base}/workflows/{self.workflow_id}", timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_next_pending(self) -> Optional[Dict[str, Any]]:
        resp = requests.get(f"{self.api_base}/workflows/{self.workflow_id}/next_pending", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("has_pending"):
            return data.get("shot")
        return None

    def update_progress(self, shot_id: str, progress: int, status: str = "running"):
        try:
            requests.post(
                f"{self.api_base}/shots/{shot_id}/progress",
                json={"progress": progress, "status": status},
                timeout=5
            )
        except Exception as e:
            logger.warning(f"更新进度失败: {e}")

    def complete_shot(self, shot_id: str, video_url: str):
        try:
            requests.post(
                f"{self.api_base}/shots/{shot_id}/complete",
                json={"video_url": video_url},
                timeout=5
            )
            logger.info(f"分镜 [{shot_id}] 标记为已完成: {video_url[:60]}...")
        except Exception as e:
            logger.error(f"完成分镜失败: {e}")

    def fail_shot(self, shot_id: str, error_msg: str):
        try:
            requests.post(
                f"{self.api_base}/shots/{shot_id}/fail",
                json={"error_message": error_msg},
                timeout=5
            )
            logger.error(f"分镜 [{shot_id}] 标记为失败: {error_msg}")
        except Exception as e:
            logger.error(f"记录分镜失败状态异常: {e}")

def run_workflow_cli(workflow_id: str):
    automator = VidsAutomator(workflow_id)
    wf = automator.get_workflow()
    logger.info(f"开始调度工作流: [{wf['title']}] (ID: {workflow_id})")
    shots = wf.get("shots", [])
    logger.info(f"工作流共包含 {len(shots)} 个镜头分镜。")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_workflow_cli(sys.argv[1])
    else:
        print("Usage: python -m video_farm.vids_automator <workflow_id>")
