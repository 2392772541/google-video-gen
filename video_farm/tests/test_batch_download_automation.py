# -*- coding: utf-8 -*-
"""
自动化测试脚本：验证 Google 视频生成控制台的批量下载 ZIP 接口与文件名规范排序逻辑
"""
import unittest
import urllib.request
import json
import zipfile
import io
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from video_farm import db
from video_farm.web import format_ordered_filename, get_task_sort_key, parse_shot_info

TARGET_TASK_IDS = [
    'task_07bf9e2c4c',  # 镜头05
    'task_185f622aee',  # 镜头04
    'task_24e39e29c9',  # 镜头03C
    'task_0616378a97',  # 镜头03B
    'task_002d0ad9b9',  # 镜头03A
]

API_BASE = 'http://127.0.0.1:8088'
DB_PATH = PROJECT_ROOT / 'video_farm_data' / 'tasks.db'


class TestBatchDownloadAutomation(unittest.TestCase):

    def setUp(self):
        self.assertTrue(DB_PATH.exists(), f'DB not found: {DB_PATH}')
        self.tasks = [db.get_task(tid, DB_PATH) for tid in TARGET_TASK_IDS]
        for tid, t in zip(TARGET_TASK_IDS, self.tasks):
            self.assertIsNotNone(t, f'Task not found: {tid}')

    def test_01_unit_sort_and_naming(self):
        """单元测试：验证分镜序号解析、排序权重及显式序数文件名前缀生成"""
        sorted_tasks = sorted(self.tasks, key=get_task_sort_key)
        
        expected_shots = ['03A', '03B', '03C', '04', '05']
        actual_shots = []
        for t in sorted_tasks:
            num, sub = parse_shot_info(t.prompt)
            actual_shots.append(f'{num:02d}{sub}')
        self.assertEqual(actual_shots, expected_shots, '分镜排序未能按 03A, 03B, 03C, 04, 05 正确排序')

        expected_prefixes = ['01_镜头03A', '02_镜头03B', '03_镜头03C', '04_镜头04', '05_镜头05']
        for idx, (t, exp_pfx) in enumerate(zip(sorted_tasks, expected_prefixes), 1):
            fn = format_ordered_filename(t, index=idx, ext='.mp4')
            self.assertTrue(fn.startswith(exp_pfx), f'{fn} 未以预期前缀 {exp_pfx} 开头')

    def test_02_api_post_batch_download_zip(self):
        """API接口测试：POST /api/tasks/batch-download-zip"""
        url = f'{API_BASE}/api/tasks/batch-download-zip'
        # 即使入参是乱序的 05, 04, 03C, 03B, 03A
        payload = json.dumps({'task_ids': TARGET_TASK_IDS}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')

        with urllib.request.urlopen(req, timeout=30) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get('Content-Type'), 'application/zip')
            
            cd = resp.headers.get('Content-Disposition')
            self.assertIn('attachment;', cd)
            self.assertIn('.zip', cd)

            data = resp.read()
            self.assertGreater(len(data), 1000)

            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                namelist = zf.namelist()
                self.assertEqual(len(namelist), 5, f'ZIP 包中文件数量不为 5: {namelist}')

                expected_prefixes = ['01_镜头03A', '02_镜头03B', '03_镜头03C', '04_镜头04', '05_镜头05']
                for name, exp_pfx in zip(namelist, expected_prefixes):
                    self.assertTrue(
                        name.startswith(exp_pfx),
                        f'ZIP 包内文件 {name} 未以正确的分镜全局序号 {exp_pfx} 开头'
                    )

    def test_03_api_get_batch_download_zip(self):
        """API接口测试：GET /api/tasks/batch-download-zip?task_ids=..."""
        query_ids = ','.join(TARGET_TASK_IDS)
        url = f'{API_BASE}/api/tasks/batch-download-zip?task_ids={query_ids}'
        req = urllib.request.Request(url, method='GET')

        with urllib.request.urlopen(req, timeout=30) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get('Content-Type'), 'application/zip')
            data = resp.read()
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                namelist = zf.namelist()
                self.assertEqual(len(namelist), 5)
                expected_prefixes = ['01_镜头03A', '02_镜头03B', '03_镜头03C', '04_镜头04', '05_镜头05']
                for name, exp_pfx in zip(namelist, expected_prefixes):
                    self.assertTrue(
                        name.startswith(exp_pfx),
                        f'ZIP 包内文件 {name} 未以正确的分镜全局序号 {exp_pfx} 开头'
                    )


if __name__ == '__main__':
    unittest.main(verbosity=2)
