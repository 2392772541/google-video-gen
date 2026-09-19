from PIL import Image

im1 = Image.open("video_farm_data/outputs/f7de0bab-4acc-4bf0-a743-c44cb50cfecb_1.jpg")
im2 = Image.open("video_farm_data/outputs/8f2bbfcf-9b86-4669-8331-175787b47de2_1.jpg")

print("促保利素 scene:", im1.size, im1.mode)
print("优根优苗 scene:", im2.size, im2.mode)
