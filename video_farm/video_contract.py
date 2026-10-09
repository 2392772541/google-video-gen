"""Provider capabilities checked before queueing and again before a worker runs."""
from pathlib import Path
import re
from PIL import Image, UnidentifiedImageError
from .models import Task


class VideoRequestError(ValueError):
    pass


def validate_video_request(task: Task, *, require_pair: bool = False) -> None:
    if task.task_type != "video":
        raise VideoRequestError("此入口只接收视频任务；生图请使用独立图像入口")
    if task.engine not in ("vids", "flow", "gemini"):
        raise VideoRequestError("未知视频平台，请选择 Google Vids、Google Flow 或 Gemini")
    if task.input_video_path and not Path(task.input_video_path).is_file():
        raise VideoRequestError("参考视频不存在或不可读取")
    if task.input_video_path and task.engine != "gemini":
        raise VideoRequestError("该平台尚未接入参考视频；请求未提交")
    if task.aspect_ratio not in ("16:9", "9:16"):
        raise VideoRequestError("视频画幅仅支持 16:9 或 9:16")
    if not 1 <= int(task.duration_sec) <= 120:
        raise VideoRequestError("视频时长格式或范围不合法")
    if not task.prompt.strip():
        raise VideoRequestError("请输入视频提示词")
    if require_pair and not (task.start_image_path and task.end_image_path):
        raise VideoRequestError("首尾帧模式必须同时提供首帧和尾帧图片")
    for label, path in (("首帧/参考图", task.start_image_path), ("尾帧", task.end_image_path)):
        if not path:
            continue
        if not Path(path).is_file():
            raise VideoRequestError(f"{label}不存在或不可读取，请重新选择图片：{path}")
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                image.load()
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise VideoRequestError(f"{label}不是可解码图片，请重新选择素材") from exc
    if task.end_image_path and task.engine not in ("flow", "vids"):
        raise VideoRequestError(
            f"Google { 'Gemini' if task.engine == 'gemini' else task.engine } 当前适配器没有尾帧绑定能力。"
            "请求未提交，也不会丢弃尾帧或自动切换平台。"
            "请显式选择 Google Flow 或 Google Vids 生成首尾帧，或移除尾帧并改用单图动画。"
        )
    if task.end_image_path and not task.start_image_path:
        raise VideoRequestError("尾帧必须与首帧一起提供")
    if task.engine == "vids":
        if task.input_video_path:
            raise VideoRequestError("Vids 视频延续尚未接入，不能按文生视频提交")
        if task.aspect_ratio not in ("16:9", "9:16"):
            raise VideoRequestError("Google Vids 仅支持 16:9 或 9:16")
        if not 3 <= int(task.duration_sec) <= 10:
            raise VideoRequestError("Google Vids 时长必须为 3 到 10 秒")
        if task.model and not re.fullmatch(r"Omni(?: \((?:720p|1080p)\))?", task.model, re.I):
            raise VideoRequestError("Google Vids 当前使用 Omni 模型，画质请选择 720p 或 1080p")
    elif task.engine == "flow":
        if int(task.duration_sec) not in (4, 6, 8, 10):
            raise VideoRequestError(f"Flow 视频时长仅支持 4、6、8、10 秒，当前为 {task.duration_sec} 秒")
        if int(task.duration_sec) == 10 and task.model and not any(k in task.model.lower() for k in ("omni-flash", "omni_flash", "omni")):
            raise VideoRequestError(f"Flow 10秒时长仅支持 Omni (omni-flash) 模型，当前模型 '{task.model}' 上限为 8 秒")
