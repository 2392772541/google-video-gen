import cv2
import numpy as np

img = cv2.imread("video_farm_data/outputs/8f2bbfcf-9b86-4669-8331-175787b47de2_1.jpg")

# In the scene, the stone pedestal is below y ≈ 705.
# At y = 400 (middle of the bag):
# Let's inspect the RGB values across x from 450 to 900 at y = 400 and y = 600
for y in [200, 400, 600]:
    row = img[y, 450:900]
    # The bag is white at top, green at bottom
    print(f"y={y}:")
    for x in range(450, 900, 20):
        b, g, r = img[y, x]
        print(f"  x={x}: B={b}, G={g}, R={r}")
