import urllib.request
import json

def req(url, method="GET", data=None):
    headers = {"Content-Type": "application/json"} if data else {}
    body = json.dumps(data).encode("utf-8") if data else None
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=5) as r:
        return r.status, r.headers, r.read().decode("utf-8")

print("=== 开始全链路 E2E 接口验收 ===")

# 1. 页面与静态资源
s, h, _ = req("http://127.0.0.1:8088/")
assert s == 200 and "no-cache" in h.get("Cache-Control", ""), "首页未配置无缓存"
print("✓ 首页 [/] 响应正常 (200, no-cache)")

s, h, _ = req("http://127.0.0.1:8088/vids")
assert s == 200 and "no-cache" in h.get("Cache-Control", ""), "Vids 页面未配置无缓存"
print("✓ 分镜工作台 [/vids] 响应正常 (200, no-cache)")

s, h, _ = req("http://127.0.0.1:8088/static/app.js")
assert s == 200 and "no-cache" in h.get("Cache-Control", ""), "静态JS未配置无缓存"
print("✓ 静态资源 [/static/app.js] 响应正常 (200, no-cache)")

# 2. 概览接口
s, _, body = req("http://127.0.0.1:8088/api/overview")
assert s == 200, "overview 失败"
ov = json.loads(body)
print("✓ 主控台概览 [/api/overview] 响应正常 (总任务: %s, 账号数: %s)" % (ov.get("total_tasks"), ov.get("total_profiles")))

s, _, body = req("http://127.0.0.1:8088/api/vids/overview")
assert s == 200, "vids overview 失败"
vov = json.loads(body)
print("✓ Vids 概览 [/api/vids/overview] 响应正常 (工作流数: %s, 总镜头数: %s)" % (vov.get("total_workflows"), vov.get("total_shots")))

# 3. 创建测试工作流
s, _, body = req("http://127.0.0.1:8088/api/vids/workflows", method="POST", data={
    "title": "E2E 验收工程 · 1080p",
    "resolution": "1080p",
    "model_name": "Omni",
    "engine": "vids"
})
assert s == 200
wf = json.loads(body)
wf_id = wf["id"]
print("✓ 创建工作流成功: [%s] %s" % (wf_id, wf["title"]))

# 4. 导入分镜（含首尾帧和单图）
s, _, body = req("http://127.0.0.1:8088/api/vids/batch_import", method="POST", data={
    "workflow_id": wf_id,
    "import_mode": "append",
    "data": [
        {
            "name": "镜头1·首尾过渡",
            "mode": "first_last_frame",
            "image_url": "start.png",
            "end_image_url": "end.png",
            "prompt": "金色麦田平滑过渡",
            "duration": 8,
            "resolution": "1080p"
        },
        {
            "name": "镜头2·单图微动",
            "mode": "image2video",
            "image_url": "single.png",
            "prompt": "阳光照射叶片",
            "duration": 6,
            "resolution": "1080p"
        }
    ]
})
assert s == 200
import_res = json.loads(body)
shots = import_res["workflow"]["shots"]
print("✓ 导入分镜成功: 成功导入 %d 个镜头" % len(shots))

# 5. 测试分镜单独生成下发与适配层自适应
shot1_id = shots[0]["id"]
s, _, body = req("http://127.0.0.1:8088/api/vids/shots/%s/generate" % shot1_id, method="POST")
assert s == 200
gen_res = json.loads(body)
print("✓ 下发镜头1任务成功: task_id=%s" % gen_res.get("task_id"))

# 6. 测试分镜强行停止
s, _, body = req("http://127.0.0.1:8088/api/vids/shots/%s/cancel" % shot1_id, method="POST")
assert s == 200
print("✓ 单镜头强行中止测试成功: %s" % json.loads(body).get("message"))

# 7. 测试工程批量停止
s, _, body = req("http://127.0.0.1:8088/api/vids/workflows/%s/stop_all" % wf_id, method="POST")
assert s == 200
print("✓ 工作流批量停止测试成功: %s" % json.loads(body).get("message"))

# 8. 清理测试工作流
s, _, _ = req("http://127.0.0.1:8088/api/vids/workflows/%s" % wf_id, method="DELETE")
assert s == 200
print("✓ 清理测试工作流成功")

# 9. 测试主控台批量导入（验证未锁死单账号）
s, _, body = req("http://127.0.0.1:8088/api/tasks/batch", method="POST", data={
    "shots": [
        {"prompt": "批量测试镜头A", "duration_sec": 8},
        {"prompt": "批量测试镜头B", "duration_sec": 8}
    ],
    "engine": "flow"
})
assert s == 200
b_res = json.loads(body)
tids = b_res["task_ids"]
assert b_res["assigned_profile_id"] is None, "批量导入依然被硬锁绑定了单账号！"
print("✓ 批量导入任务成功: %d 个任务已进入队列，assigned_profile_id 为 None (保持账号池动态抢占)" % len(tids))

# 10. 测试批量取消
s, _, body = req("http://127.0.0.1:8088/api/tasks/batch/cancel", method="POST", data={"task_ids": tids})
assert s == 200
print("✓ 批量取消测试成功: %s" % json.loads(body).get("message"))

print("=== 全链路 E2E 接口验收全部通过 (100% SUCCESS) ===")
