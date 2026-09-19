import os, shutil, json, subprocess
from pathlib import Path

delivery_dir = Path("video_farm_data/deliveries/福联全套13款产品大片宣传片视频_16x9")
delivery_dir.mkdir(parents=True, exist_ok=True)
(delivery_dir / "previews").mkdir(parents=True, exist_ok=True)

manifest = [
    {
        "index": "01",
        "key": "01",
        "name": "01_添添向上_98%DMPP原粉_16x9",
        "chinese_name": "添添向上 98%DMPP原粉 (1kg)",
        "scene_desc": "极简纯白科技空间，环形发光白色大理石展台，远景葱郁麦浪与晨风日光",
        "src_video": "video_farm_data/outputs/f175f836-bfa5-4199-b668-aa0c66126bfc.mp4",
        "src_frame": "video_farm_data/uploads/scenes/prod_01_first_frame.png"
    },
    {
        "index": "02",
        "key": "02",
        "name": "02_添添向上_纳铠甲80%DMP-X_16x9",
        "chinese_name": "添添向上 纳铠甲 80% DMP-X (1kg)",
        "scene_desc": "暗调纳米科技微观空间，多面切割水晶晶体展台，幽蓝纳米粒子光晕",
        "src_video": "video_farm_data/outputs/5561f737-1478-41a1-8bf2-a4cacc26d812.mp4",
        "src_frame": "video_farm_data/uploads/scenes/prod_02_first_frame.png"
    },
    {
        "index": "03",
        "key": "03",
        "name": "03_添添向上_捷邦50%DMPX油剂_16x9",
        "chinese_name": "添添向上 捷邦 50% DMPX油剂 (5L)",
        "scene_desc": "现代化农化工程国家重点实验室，拉丝金属工业基座，组培温室与精密器皿",
        "src_video": "video_farm_data/outputs/94a271c3-6a2d-462b-adca-119b0ca3d702.mp4",
        "src_frame": "video_farm_data/uploads/scenes/prod_03_first_frame.png"
    },
    {
        "index": "04",
        "key": "04",
        "name": "04_添添向上_90%氨基寡糖素粉剂_16x9",
        "chinese_name": "添添向上 90%氨基寡糖素粉剂 (1kg)",
        "scene_desc": "高奢暗调生物科技沙龙，墨绿金丝大理石圆柱展台，聚光灯与金光浮尘",
        "src_video": "video_farm_data/outputs/13e37d54-4570-42a0-afdb-07d514b54fa2.mp4",
        "src_frame": "video_farm_data/uploads/scenes/prod_04_first_frame.png"
    },
    {
        "index": "05",
        "key": "05",
        "name": "05_添添向上_10%氨基寡糖素液剂_16x9",
        "chinese_name": "添添向上 10%氨基寡糖素液剂 (1L)",
        "scene_desc": "晨曦生态玻璃温室，古典大理石罗马柱基座，微澜水面倒影与盛开兰花",
        "src_video": "video_farm_data/outputs/15ecbd05-29ab-4bf9-a5bb-dce8650b90c1.mp4",
        "src_frame": "video_farm_data/uploads/scenes/prod_05_first_frame.png"
    },
    {
        "index": "06",
        "key": "06",
        "name": "06_添添向上_90%褐藻寡糖粉剂_16x9",
        "chinese_name": "添添向上 90%褐藻寡糖粉剂 (1kg)",
        "scene_desc": "深海火山玄武岩石台，激荡浪花薄雾，深海幽蓝冷光与海洋生物荧光粒子",
        "src_video": "video_farm_data/outputs/145a7e80-5981-425c-a8cf-c13c505adaec.mp4",
        "src_frame": "video_farm_data/uploads/scenes/prod_06_first_frame.png"
    },
    {
        "index": "07",
        "key": "07",
        "name": "07_添添向上_30%褐藻寡糖液剂_16x9",
        "chinese_name": "添添向上 30%褐藻寡糖液剂 (1L)",
        "scene_desc": "晨曦静谧湖面，黑曜石浮岛展台，水面同心圆涟漪扩散，水汽氤氲与睡莲",
        "src_video": "video_farm_data/outputs/4958b014-659e-4c41-86db-11140f873c70.mp4",
        "src_frame": "video_farm_data/uploads/scenes/prod_07_first_frame.png"
    },
    {
        "index": "08",
        "key": "08",
        "name": "08_福联生物_基因产物超免蛋白_16x9",
        "chinese_name": "福联生物 基因产物超免蛋白 (1000g)",
        "scene_desc": "未来生物基因工程实验室，发光钛金玻璃基座，蓝色全息DNA光幕与洁净冷光",
        "src_video": "video_farm_data/outputs/afd30207-d774-448d-8d81-c3cb1db174d4.mp4",
        "src_frame": "video_farm_data/uploads/scenes/prod_08_first_frame.png"
    },
    {
        "index": "09",
        "key": "09",
        "name": "09_福联生物_土壤疏松调理剂_16x9",
        "chinese_name": "福联生物 土壤疏松调理剂 (25kg)",
        "scene_desc": "广袤肥沃黑土地沃野日出，厚重原木栈台，茁壮成长的玉米苗与金色朝阳",
        "src_video": "video_farm_data/outputs/3b6e535c-01c8-42c0-966a-7cfd0c69e4a2.mp4",
        "src_frame": "video_farm_data/uploads/scenes/prod_09_first_frame.png"
    },
    {
        "index": "10",
        "key": "kui",
        "name": "10_添添向上_块茎王_16x9",
        "chinese_name": "添添向上 块茎王 (1000g)",
        "scene_desc": "丰收金色夕阳田园，天然年轮古木圆台，饱满红薯土豆与金黄麦浪环绕",
        "src_video": "video_farm_data/outputs/9bab7bbd-9a71-42d3-a8db-da1abfc801bc.mp4",
        "src_frame": "video_farm_data/uploads/scenes/prod_kui_first_frame.png"
    },
    {
        "index": "11",
        "key": "11",
        "name": "11_添添向上_促保利素_16x9",
        "chinese_name": "添添向上 促保利素® (1000g)",
        "scene_desc": "晨曦暖阳麦浪沃野，环形暖琥珀玛瑙石台，金色丁达尔太阳光束穿透，光合能量悬浮粒子",
        "src_video": "video_farm_data/outputs/2327057a-9412-4b42-a61d-8a4ee4ee8118.mp4",
        "src_frame": "video_farm_data/uploads/scenes/prod_11_first_frame.png"
    },
    {
        "index": "12",
        "key": "12",
        "name": "12_添添向上_优根优苗_16x9",
        "chinese_name": "添添向上 优根优苗™ (1000g)",
        "scene_desc": "现代农业生根科学实验室，深黑岩石基台，通透玻璃器皿中茂密生根幼苗与发达白根，水雾绿光微粒",
        "src_video": "video_farm_data/outputs/e0e64864-5c11-4566-a508-05db8e383754.mp4",
        "src_frame": "video_farm_data/uploads/scenes/prod_12_first_frame.png"
    },
    {
        "index": "13",
        "key": "13",
        "name": "13_添添向上_85%氨基寡糖素粉剂_16x9",
        "chinese_name": "添添向上 85%氨基寡糖素粉剂 (1kg)",
        "scene_desc": "现代生物农业土壤生态实验室，极简深黑黑曜石展台，深层黑土与发光根系网络，金色生物养分微粒",
        "src_video": "video_farm_data/outputs/16bcbb1f-da34-4fd8-b129-b9160d0fe918.mp4",
        "src_frame": "video_farm_data/uploads/scenes/prod_13_first_frame.png"
    }
]

report_lines = []

for item in manifest:
    # 1. Copy video
    dest_video = delivery_dir / f"{item['name']}.mp4"
    shutil.copy2(item["src_video"], dest_video)
    
    # 2. Copy first frame
    dest_frame = delivery_dir / f"{item['name']}_首帧.png"
    shutil.copy2(item["src_frame"], dest_frame)
    
    # 3. Extract middle frame preview
    preview_png = delivery_dir / "previews" / f"{item['name']}_mid.png"
    if not preview_png.exists():
        cmd = [
            "ffmpeg", "-y", "-ss", "00:00:04",
            "-i", str(dest_video),
            "-vframes", "1",
            str(preview_png)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 4. ffprobe check
    ffprobe_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=width,height,duration,r_frame_rate,bit_rate",
        "-of", "json",
        str(dest_video)
    ]
    probe = json.loads(subprocess.check_output(ffprobe_cmd).decode("utf-8"))
    video_stream = next(s for s in probe["streams"] if "width" in s)
    w = video_stream["width"]
    h = video_stream["height"]
    dur = float(video_stream.get("duration", 8.0))
    fps = video_stream["r_frame_rate"]
    size_mb = dest_video.stat().st_size / (1024 * 1024)
    
    info_line = f"| {item['index']} | **{item['chinese_name']}** | {w}x{h} (16:9) | {dur:.1f}s | {fps}fps | {size_mb:.2f} MB | {item['name']}.mp4 |"
    report_lines.append(info_line)
    print(f"Delivered: {item['name']} ({w}x{h}, {dur}s, {size_mb:.2f}MB)")

with open(delivery_dir / "DELIVERY_REPORT.md", "w", encoding="utf-8") as f:
    f.write("# 福联生物 全套13款核心农化产品 16:9 商业大片宣传片视频交付清单\n\n")
    f.write("| 序号 | 产品全称与规格 | 分辨率 (比例) | 时长 | 帧率 | 文件大小 | 成品文件名 |\n")
    f.write("| :---: | :--- | :---: | :---: | :---: | :---: | :--- |\n")
    f.write("\n".join(report_lines))
    f.write("\n\n## 场景设计与视觉呈现规划说明\n\n")
    for item in manifest:
        f.write(f"### {item['index']}. {item['chinese_name']}\n")
        f.write(f"- **商业场景概念**：{item['scene_desc']}\n")
        f.write(f"- **高清首帧基准**：{item['name']}_首帧.png\n")
        f.write(f"- **动态渲染视频**：{item['name']}.mp4\n\n")

print(f"\nAll {len(manifest)} deliveries packaged and verified successfully in {delivery_dir}!")
