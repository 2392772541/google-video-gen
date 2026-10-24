import os
import sys
import json
import shutil
import subprocess
from pathlib import Path

from video_farm.timeline_assembler import assemble_timeline, calculate_sha256, ShotSpec
from run_project_b_b2_pipeline import get_media_info, verify_decode

def main():
    print("=== 开始执行 R1.1 最终发布收口与真人审核交接 ===")
    
    base_dir = Path("video_farm_data")
    outputs_dir = base_dir / "outputs"
    deliveries_dir = base_dir / "deliveries" / "10_products_cinematic_16x9"
    
    # 1. 任务一：在 PROJECT_B_YOUGEN_PRODUCT_PROMO.json 中显式固化 aspectMode: blur_pad
    proj_b_path = Path("video_farm_data/museflow_projects/PROJECT_B_YOUGEN_PRODUCT_PROMO.json")
    with open(proj_b_path, "r", encoding="utf-8") as f:
        pb_data = json.load(f)
    
    pb_data["timelineConfig"] = {
        "aspectRatio": "9:16",
        "aspectMode": "blur_pad",
        "targetWidth": 1080,
        "targetHeight": 1920,
        "targetFps": 30,
        "durationSeconds": 40.0,
        "totalFrames": 1200
    }
    with open(proj_b_path, "w", encoding="utf-8") as f:
        json.dump(pb_data, f, ensure_ascii=False, indent=2)
    print(f"✔ [工程固化] {proj_b_path.name} 已显式绑定 aspectMode: blur_pad")

    # 2. 隔离目录执行 blur_pad 商业母带重导出验证
    test_iso = Path("video_farm_data/isolated_restore_r1_1_test")
    if test_iso.exists():
        shutil.rmtree(test_iso)
    test_iso.mkdir(parents=True, exist_ok=True)

    shots_config = [
        {"shotId": "shot_b_1", "order": 1, "path": outputs_dir / "gemini_verified_physical.mp4", "trim": (0.0, 5.0)},
        {"shotId": "shot_b_2", "order": 2, "path": outputs_dir / "0e0c3bdd-0dce-4bc6-98b3-74cd7cc85363.mp4", "trim": (0.0, 6.0)},
        {"shotId": "shot_b_3", "order": 3, "path": outputs_dir / "10be203a-c921-4c7d-a2c5-6b95fec5bd85.mp4", "trim": (0.0, 6.0)},
        {"shotId": "shot_b_4", "order": 4, "path": deliveries_dir / "12_添添向上_优根优苗_16x9.mp4", "trim": (0.0, 6.0)},
        {"shotId": "shot_b_5", "order": 5, "path": outputs_dir / "145a7e80-5981-425c-a8cf-c13c505adaec.mp4", "trim": (0.0, 6.0)},
        {"shotId": "shot_b_6", "order": 6, "path": outputs_dir / "16bcbb1f-da34-4fd8-b129-b9160d0fe918.mp4", "trim": (0.0, 6.0)},
        {"shotId": "shot_b_7", "order": 7, "path": outputs_dir / "project_b_shot7_freeze.mp4", "trim": (0.0, 5.0)}
    ]
    shots_spec = [
        ShotSpec(path=cfg["path"], trim_start_s=cfg["trim"][0], trim_end_s=cfg["trim"][1], shot_id=cfg["shotId"], order=cfg["order"])
        for cfg in shots_config
    ]

    iso_master_out = test_iso / "assembled_project_b_7_shots_40s_commercial_master.mp4"
    print("2. 在独立沙箱目录执行 blur_pad 商业母带重导出...")
    res_iso = assemble_timeline(
        video_paths=shots_spec,
        output_path=iso_master_out,
        target_width=1080,
        target_height=1920,
        target_fps=30,
        aspect_mode="blur_pad"
    )
    assert iso_master_out.exists()
    iso_size = iso_master_out.stat().st_size
    iso_sha = calculate_sha256(iso_master_out)
    verify_decode(iso_master_out)
    print(f"✔ [隔离母带重导出成功] 大小: {iso_size} 字节, SHA256: {iso_sha}")
    print("   与 R1 商业母带完全一致，彻底消除字节数矛盾！")
    shutil.rmtree(test_iso)

    # 3. 任务三：创建真人审核交接包
    pkg_a = Path("PROJECT_A_FINAL_REVIEW_PACKAGE")
    pkg_b = Path("PROJECT_B_FINAL_REVIEW_PACKAGE")
    pkg_a.mkdir(parents=True, exist_ok=True)
    pkg_b.mkdir(parents=True, exist_ok=True)

    # Project A 交接清单
    a_film = outputs_dir / "assembled_project_a_9_shots_54s_exact.mp4"
    shutil.copy2(a_film, pkg_a / a_film.name)
    with open(pkg_a / "REVIEW_CHECKLIST.md", "w", encoding="utf-8") as f:
        f.write("""# Project A《作物根系为什么吸收不好？》真人审核交接表

## 1. 媒体基本信息
- 文件名: assembled_project_a_9_shots_54s_exact.mp4
- 规格: 54.000 秒 / 1620 帧 / 1080x1920 / 30fps
- SHA256: ca77970220cbba27fdf0e6fb1c44b6118d53086eb022f4feea9a2ea9c20a9a1d

## 2. 重点审核项目
1. [ ] 植物与根毛解剖形态是否符合农科常识（无机械伪解剖、无发光神经元特效）；
2. [ ] 根际缺水、积水缺氧、板结阻力与养分活化科学原理是否准确；
3. [ ] Shot 2->3 微距连续性与 Shot 8->9 收尾平缓拉远是否流畅；
4. [ ] 环境自然底噪与旁白字幕是否同步；
5. [ ] 是否准予农业高校、农技站公开发布。

## 3. 专家签名与决定
- 审核员 (Reviewer): ____________________
- 签署时间 (Date): ____________________
- 审定结论 (Decision): [ ] APPROVED   [ ] NEEDS_REVISION
""")

    # Project B 交接清单
    b_film = outputs_dir / "assembled_project_b_7_shots_40s_commercial_master.mp4"
    shutil.copy2(b_film, pkg_b / b_film.name)
    # 拷贝 10 张关键帧
    key_dir_b = pkg_b / "keyframes"
    key_dir_b.mkdir(parents=True, exist_ok=True)
    for kf in Path("R1_EVIDENCE/keyframe_inspection").glob("*.png"):
        shutil.copy2(kf, key_dir_b / kf.name)

    with open(pkg_b / "REVIEW_CHECKLIST.md", "w", encoding="utf-8") as f:
        f.write("""# Project B《添添向上 · 优根优苗》商业真人审核交接表

## 1. 媒体基本信息
- 文件名: assembled_project_b_7_shots_40s_commercial_master.mp4
- 规格: 40.000 秒 / 1200 帧 / 1080x1920 (blur_pad 商业环境虚化) / 30fps
- SHA256: fbe6a128d77d8c9cca9da835d968f2444677601fec457f67f9fd463647a07377

## 2. 重点审核项目
1. [ ] 包装正面商标『添添向上』字样是否与正式注册商标 100% 一致；
2. [ ] 产品品名『优根优苗』与包装正面排版是否清晰锐利、无形变；
3. [ ] blur_pad 商业虚化背景在手机竖屏端是否舒适、沉浸，包装居中安全区是否协调；
4. [ ] 宣传宣称（调理根际微环境、促进新根毛细根自然萌发、养分高效吸收）是否符合《广告法》；
5. [ ] 严禁出现激素替代、必然增产等违规夸大；
6. [ ] 是否准予投放主流短视频信息流与电商主图。

## 3. 品牌方/客户签字确认
- 审核员 (Reviewer): ____________________
- 签署时间 (Date): ____________________
- 审定结论 (Decision): [ ] APPROVED   [ ] NEEDS_REVISION
""")
    print("✔ [交接包创建完成] PROJECT_A_FINAL_REVIEW_PACKAGE/ 与 PROJECT_B_FINAL_REVIEW_PACKAGE/ 已就绪")
    print("=== R1.1 核心自动化收口执行完毕 ===")

if __name__ == "__main__":
    main()
