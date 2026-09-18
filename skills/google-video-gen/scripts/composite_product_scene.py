"""
composite_product_scene.py
--------------------------
Zero AI Distortion (零 AI 畸变) 商业级首帧复合工具。
使用 OpenCV 多尺度模板匹配与精确几何对齐，将真实官方产品包装（透明背景 PNG）
以像素级精度无损覆盖并融入 AI 生成的商业级展台底图上。

功能特性：
1. 完全避免 AI 直接生成中文包装导致的文字乱码、字体变形、商标走样问题。
2. 彻底告别传统“粗暴绿地贴图”的廉价感，实现真正千万级商业大片质感。
3. 原生支持 Windows 中文绝对路径（np.fromfile + cv2.imdecode/imencode）。
4. 双模式支持：
   - match: 自动在垫图生成的场景中通过多尺度归一化互相关 (TM_CCOEFF_NORMED) 搜索 AI 展台上的产品位置并精准替换。
   - dock:  对空展台场景，按指定比例或展台中心与底部基准面自动对齐贴合。
"""

import sys
import os
import argparse
import cv2
import numpy as np
from PIL import Image

def load_img_unicode(path: str, flags=cv2.IMREAD_UNCHANGED):
    """支持 Windows 复杂中文路径读取图像"""
    try:
        if not os.path.exists(path):
            return None
        data = np.fromfile(path, dtype=np.uint8)
        return cv2.imdecode(data, flags)
    except Exception as e:
        print(f"[Error] 读取图片失败 [{path}]: {e}")
        return None

def save_img_unicode(img_pil: Image.Image, out_path: str):
    """支持 Windows 复杂中文路径保存图像"""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img_pil.save(out_path)

def extract_valid_box(ref_img):
    """提取透明通道中非透明内容的外接矩形与裁切"""
    if ref_img.shape[2] == 4:
        alpha = ref_img[:, :, 3]
        ys, xs = np.where(alpha > 15)
        if len(ys) > 0 and len(xs) > 0:
            return ref_img[ys.min():ys.max()+1, xs.min():xs.max()+1], (xs.min(), ys.min(), xs.max()-xs.min()+1, ys.max()-ys.min()+1)
    return ref_img, (0, 0, ref_img.shape[1], ref_img.shape[0])

def find_product_box_ncc(scene_path: str, ref_path: str, min_h=300, max_h=700, step=5):
    """
    在 AI 生成的场景图中多尺度搜索产品外包位置
    返回: (best_x, best_y, best_scale, best_score)
    """
    scene = load_img_unicode(scene_path, cv2.IMREAD_COLOR)
    ref = load_img_unicode(ref_path, cv2.IMREAD_UNCHANGED)
    if scene is None:
        raise FileNotFoundError(f"场景底图不存在: {scene_path}")
    if ref is None:
        raise FileNotFoundError(f"产品包装参考图不存在: {ref_path}")

    ref_cropped, (ox, oy, ow, oh) = extract_valid_box(ref)

    ref_gray = cv2.cvtColor(ref_cropped[:, :, :3], cv2.COLOR_BGR2GRAY)
    scene_gray = cv2.cvtColor(scene, cv2.COLOR_BGR2GRAY)

    sh, sw = scene_gray.shape
    # 展台一般在场景中间区域：X 在 15%~85%，Y 在 2%~98%
    roi_x1 = int(sw * 0.15)
    roi_x2 = int(sw * 0.85)
    roi_y1 = int(sh * 0.02)
    roi_y2 = int(sh * 0.98)
    search_region = scene_gray[roi_y1:roi_y2, roi_x1:roi_x2]

    best_val = -1.0
    best_scale = None
    best_loc = None

    orig_h = ref_cropped.shape[0]
    for target_h in range(min_h, min(max_h, roi_y2 - roi_y1), step):
        scale = target_h / orig_h
        target_w = int(ref_cropped.shape[1] * scale)
        if target_w >= (roi_x2 - roi_x1):
            continue

        resized_template = cv2.resize(ref_gray, (target_w, target_h), interpolation=cv2.INTER_AREA)
        res = cv2.matchTemplate(search_region, resized_template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        if max_val > best_val:
            best_val = max_val
            best_scale = scale
            # 换算回全图坐标（由于模板是 cropped 区域，需要对应推导原始图左上角位置）
            best_loc = (max_loc[0] + roi_x1 - int(ox * scale), max_loc[1] + roi_y1 - int(oy * scale))

    return best_loc, best_scale, best_val

def composite_scene(scene_path: str, ref_path: str, out_path: str, 
                    mode="match", loc=None, scale=None, 
                    target_width=None, bottom_offset=0.15):
    """
    执行合成：
    - mode="match": NCC 自动模板匹配
    - mode="dock": 居中底托吸附 (基于 bottom_offset 百分比)
    """
    scene_im = Image.open(scene_path).convert("RGBA")
    ref_im = Image.open(ref_path).convert("RGBA")

    sw, sh = scene_im.size
    rw, rh = ref_im.size

    if loc is not None and scale is not None:
        target_w = int(rw * scale)
        target_h = int(rh * scale)
        pos = loc
    elif mode == "match":
        best_loc, best_scale, score = find_product_box_ncc(scene_path, ref_path)
        print(f"[Match] NCC 最佳匹配度: {score:.4f}, 位置: {best_loc}, 缩放: {best_scale:.4f}")
        if score < 0.25 and (loc is None):
            print("[Warning] 模板匹配置信度较低，建议检查场景图或使用 dock 模式指定对齐！")
        scale = best_scale if best_scale else (sh * 0.75 / rh)
        target_w = int(rw * scale)
        target_h = int(rh * scale)
        pos = best_loc if best_loc else ((sw - target_w) // 2, int(sh * (1.0 - bottom_offset) - target_h))
    else: # dock mode
        if target_width:
            target_w = int(target_width)
            scale = target_w / rw
            target_h = int(rh * scale)
        elif scale is not None:
            target_w = int(rw * scale)
            target_h = int(rh * scale)
        else:
            # 默认占据画幅高度的 68%~75%
            target_h = int(sh * 0.70)
            scale = target_h / rh
            target_w = int(rw * scale)

        pos_x = (sw - target_w) // 2
        pos_y = int(sh * (1.0 - bottom_offset) - target_h)
        pos = (pos_x, pos_y)
        print(f"[Dock] 居中基座对齐: 位置={pos}, 尺寸=({target_w}x{target_h}), 缩放={scale:.4f}")

    ref_resized = ref_im.resize((target_w, target_h), Image.Resampling.LANCZOS)
    composite_im = scene_im.copy()
    composite_im.paste(ref_resized, pos, ref_resized)

    save_img_unicode(composite_im, out_path)
    print(f"[Success] 复合首帧成功生成: {out_path} ({composite_im.size})")
    return out_path

def main():
    parser = argparse.ArgumentParser(description="Zero AI Distortion 商业级首帧复合工具")
    parser.add_argument("--scene", required=True, help="AI 生成的场景底图路径")
    parser.add_argument("--product", required=True, help="官方原版透明底包装 PNG 路径")
    parser.add_argument("--out", required=True, help="输出的高清首帧图片路径")
    parser.add_argument("--mode", choices=["match", "dock"], default="match", help="合成对齐模式: match (模板匹配), dock (居中吸附)")
    parser.add_argument("--scale", type=float, default=None, help="手动指定缩放比例")
    parser.add_argument("--pos-x", type=int, default=None, help="手动指定 X 坐标")
    parser.add_argument("--pos-y", type=int, default=None, help="手动指定 Y 坐标")
    parser.add_argument("--target-width", type=int, default=None, help="指定产品放置宽度 (像素)")
    parser.add_argument("--bottom-offset", type=float, default=0.15, help="展台承重基线距底部百分比 (默认 0.15)")

    args = parser.parse_args()

    loc = (args.pos_x, args.pos_y) if (args.pos_x is not None and args.pos_y is not None) else None
    composite_scene(
        scene_path=args.scene,
        ref_path=args.product,
        out_path=args.out,
        mode=args.mode,
        loc=loc,
        scale=args.scale,
        target_width=args.target_width,
        bottom_offset=args.bottom_offset
    )

if __name__ == "__main__":
    main()
