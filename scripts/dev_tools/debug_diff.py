import cv2
import numpy as np

ai_scene = cv2.imread("video_farm_data/outputs/8f2bbfcf-9b86-4669-8331-175787b47de2_1.jpg")
comp_first = cv2.imread("video_farm_data/uploads/scenes/prod_12_first_frame.png")

# Difference image
diff = cv2.absdiff(ai_scene, comp_first)
cv2.imwrite("video_farm_data/debug_yougen/diff_scene_comp.png", diff)

# Crop the region around x=480:880, y=50:730
cv2.imwrite("video_farm_data/debug_yougen/crop_ai_scene.png", ai_scene[50:730, 480:880])
cv2.imwrite("video_farm_data/debug_yougen/crop_comp_first.png", comp_first[50:730, 480:880])
print("Saved comparison crops.")
