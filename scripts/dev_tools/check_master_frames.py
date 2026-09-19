import subprocess, os

os.makedirs('build_6ba/master_previews', exist_ok=True)
timestamps = [2.0, 8.0, 15.0, 21.0, 27.0, 32.0, 38.0, 43.5]
video_path = r'build_6ba\6BA_45s_科学纪录片_成片_1080p.mp4'

for ts in timestamps:
    out_png = f'build_6ba/master_previews/frame_{ts:.1f}s.png'
    subprocess.run(['ffmpeg', '-y', '-ss', str(ts), '-i', video_path, '-vframes', '1', out_png], capture_output=True)
    print(f'Extracted {out_png}')
