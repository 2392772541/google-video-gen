import cv2
import numpy as np

img = cv2.imread("video_farm_data/outputs/8f2bbfcf-9b86-4669-8331-175787b47de2_1.jpg")
h, w = img.shape[:2]

# Let's inspect rows 60 to 720 and cols 400 to 900
# The bag has white and green.
# Let's print out where the bag edges are
print("Image shape:", img.shape)
