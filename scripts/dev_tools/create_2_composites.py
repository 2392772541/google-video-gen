from PIL import Image

coords = {
    "11": {
        "px": 523,
        "py": 65,
        "tw": 321,
        "scene": "video_farm_data/outputs/f7de0bab-4acc-4bf0-a743-c44cb50cfecb_1.jpg",
        "ref": r"E:\公司素材\产品实景图\最新定稿图\福联\促保利素\促保利素.png",
        "out": "video_farm_data/uploads/scenes/prod_11_first_frame.png"
    },
    "12": {
        "px": 519,
        "py": 74,
        "tw": 312,
        "scene": "video_farm_data/outputs/8f2bbfcf-9b86-4669-8331-175787b47de2_1.jpg",
        "ref": r"E:\公司素材\产品实景图\最新定稿图\福联\优根优苗\优根优苗__copy.png",
        "out": "video_farm_data/uploads/scenes/prod_12_first_frame.png"
    }
}

for k, v in coords.items():
    scene = Image.open(v["scene"]).convert("RGBA")
    ref = Image.open(v["ref"]).convert("RGBA")
    
    th = int(ref.height * (v["tw"] / ref.width))
    ref_resized = ref.resize((v["tw"], th), Image.Resampling.LANCZOS)
    
    comp = scene.copy()
    comp.paste(ref_resized, (v["px"], v["py"]), ref_resized)
    
    comp.save(v["out"])
    print(f"Saved: {v['out']} ({comp.size})")
