import subprocess, os

clips = {
    'Section_A': r'C:\Users\win10\Documents\ChatGPT\视频制作\video_farm_data\outputs\e945854d-dd57-48a4-be40-1c748432e27f.mp4',
    'Section_B': r'C:\Users\win10\Documents\ChatGPT\视频制作\video_farm_data\outputs\dfdb819b-7528-4dea-a3ca-b79002c2ce7f.mp4',
    'Section_C': r'C:\Users\win10\Documents\ChatGPT\视频制作\video_farm_data\outputs\738469ab-5dc5-4eae-b585-7ddc5c3e2a9d.mp4'
}

os.makedirs('build_6ba/ai_previews', exist_ok=True)
for name, p in clips.items():
    out_png = f'build_6ba/ai_previews/{name}_mid.png'
    subprocess.run(['ffmpeg', '-y', '-ss', '4.0', '-i', p, '-vframes', '1', out_png], capture_output=True)
    print(f'Extracted {name} mid-frame -> {out_png}')
