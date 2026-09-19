import cv2
import numpy as np
from PIL import Image

def load_img(path, flags=cv2.IMREAD_UNCHANGED):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), flags)

def find_product_box(scene_path, ref_path):
    scene = load_img(scene_path, cv2.IMREAD_COLOR)
    ref = load_img(ref_path, cv2.IMREAD_UNCHANGED)
    
    # Extract alpha mask
    if ref.shape[2] == 4:
        alpha = ref[:, :, 3]
        ys, xs = np.where(alpha > 10)
        ref_cropped = ref[ys.min():ys.max()+1, xs.min():xs.max()+1]
    else:
        ref_cropped = ref
        
    ref_gray = cv2.cvtColor(ref_cropped[:, :, :3], cv2.COLOR_BGR2GRAY)
    scene_gray = cv2.cvtColor(scene, cv2.COLOR_BGR2GRAY)
    
    best_val = -1
    best_scale = None
    best_loc = None
    
    # Test scales corresponding to product height between 350 and 650 px in a 768px image
    orig_h = ref_cropped.shape[0]
    for target_h in range(350, 680, 5):
        scale = target_h / orig_h
        target_w = int(ref_cropped.shape[1] * scale)
        resized_template = cv2.resize(ref_gray, (target_w, target_h))
        
        # Search region: x from 300 to 1100, y from 10 to 740
        search_region = scene_gray[10:740, 300:1100]
        if search_region.shape[0] < target_h or search_region.shape[1] < target_w:
            continue
            
        res = cv2.matchTemplate(search_region, resized_template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        
        if max_val > best_val:
            best_val = max_val
            best_scale = scale
            best_loc = (max_loc[0] + 300, max_loc[1] + 10)
            
    return best_loc, best_scale, best_val

items = {
    "11": {
        "name": "促保利素",
        "scene": "video_farm_data/outputs/f7de0bab-4acc-4bf0-a743-c44cb50cfecb_1.jpg",
        "ref": r"E:\公司素材\产品实景图\最新定稿图\福联\促保利素\促保利素.png"
    },
    "12": {
        "name": "优根优苗",
        "scene": "video_farm_data/outputs/8f2bbfcf-9b86-4669-8331-175787b47de2_1.jpg",
        "ref": r"E:\公司素材\产品实景图\最新定稿图\福联\优根优苗\优根优苗__copy.png"
    }
}

for k, v in items.items():
    loc, scale, score = find_product_box(v["scene"], v["ref"])
    ref_im = Image.open(v["ref"])
    target_w = int(ref_im.width * scale) if scale else None
    target_h = int(ref_im.height * scale) if scale else None
    print(f"[{k} - {v['name']}] score={score:.4f}, loc={loc}, scale={scale:.4f}, target_size=({target_w}, {target_h})")
