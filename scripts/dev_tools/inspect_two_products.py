from PIL import Image
import os

p1 = r"E:\公司素材\产品实景图\最新定稿图\福联\促保利素\促保利素.png"
p2 = r"E:\公司素材\产品实景图\最新定稿图\福联\优根优苗\优根优苗__copy.png"

for p in [p1, p2]:
    if os.path.exists(p):
        im = Image.open(p)
        print(os.path.basename(p), im.size, im.mode)
    else:
        print("NOT FOUND:", p)
