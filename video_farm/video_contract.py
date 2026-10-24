"""Provider capabilities checked before queueing and again before a worker runs."""
from pathlib import Path
import re
from PIL import Image, UnidentifiedImageError, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True
from .models import Task


class VideoRequestError(ValueError):
    pass

SUPPORTED_IMAGE_FORMATS = {"JPEG", "JPG", "PNG", "WEBP"}
MAX_IMAGE_BYTES = 32 * 1024 * 1024  # 32MB
MIN_IMAGE_DIMENSION = 1
MAX_IMAGE_DIMENSION = 8192
MAX_ASPECT_RATIO = 16.0


def validate_image_file(path_str: str, label: str = "参考图片") -> None:
    if not path_str:
        return
    path = Path(path_str)
    if not path.is_file():
        raise VideoRequestError(f"{label}不存在或不可读取，请重新选择图片：{path_str}")
    size = path.stat().st_size
    if size == 0:
        raise VideoRequestError(f"{label}文件内容为空 (0 字节)，请上传有效图片")
    if size > MAX_IMAGE_BYTES:
        raise VideoRequestError(
            f"{label}体积超过限制 ({size / (1024 * 1024):.1f}MB)，单张图片最大支持 32MB"
        )
    try:
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        with Image.open(str(path)) as image:
            fmt = (image.format or "").upper()
            if fmt not in SUPPORTED_IMAGE_FORMATS:
                raise VideoRequestError(
                    f"{label}格式不支持 ({fmt or '未知格式'})，仅支持 JPG、PNG、WEBP 格式图片"
                )
            try:
                image.verify()
            except Exception:
                pass
        with Image.open(str(path)) as image:
            image.load()
            w, h = image.size
            if w < MIN_IMAGE_DIMENSION or h < MIN_IMAGE_DIMENSION:
                raise VideoRequestError(
                    f"{label}分辨率过低 ({w}x{h})，宽高均需至少 {MIN_IMAGE_DIMENSION} 像素"
                )
            if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
                raise VideoRequestError(
                    f"{label}单边分辨率超过上限 ({w}x{h})，单边最大支持 {MAX_IMAGE_DIMENSION} 像素"
                )
            aspect = max(w, h) / max(1, min(w, h))
            if aspect > MAX_ASPECT_RATIO:
                raise VideoRequestError(
                    f"{label}长宽比异常 ({w}:{h})，不支持极端狭长图片，建议使用标准比例素材"
                )
    except VideoRequestError:
        raise
    except Exception as exc:
        raise VideoRequestError(f"{label}不是可解码图片，请重新选择素材: {exc}") from exc


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
    
    start_paths = [p.strip() for p in (task.start_image_path or "").split(";") if p.strip()]
    for idx, path in enumerate(start_paths):
        lbl = "首帧/参考图" if len(start_paths) == 1 else f"参考图 {idx+1}"
        validate_image_file(path, lbl)
    if task.end_image_path:
        validate_image_file(task.end_image_path, "尾帧")

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
        if len(start_paths) > 3:
            raise VideoRequestError("Google Vids 当前最多支持 3 张参考图，请减少参考图数量")
    elif task.engine == "flow":
        if int(task.duration_sec) not in (4, 6, 8, 10):
            raise VideoRequestError(f"Flow 视频时长仅支持 4、6、8、10 秒，当前为 {task.duration_sec} 秒")
        if int(task.duration_sec) == 10 and task.model and not any(k in task.model.lower() for k in ("omni-flash", "omni_flash", "omni", "flow")):
            raise VideoRequestError(f"Flow 10秒时长仅支持 Omni (omni-flash) 模型，当前模型 '{task.model}' 仅支持 4s/6s/8s")
        
        if len(start_paths) > 1 and not task.end_image_path:
            raw_m = (task.model or "").lower()
            if "quality" in raw_m:
                raise VideoRequestError("Flow Veo Quality 模型不支持参考图 (Ingredients) 生成，请切换为 Veo Fast / Lite 或 Omni 模型，或改用首尾帧模式")
            elif any(k in raw_m for k in ("omni-flash", "omni_flash", "omni")):
                if len(start_paths) > 3:
                    raise VideoRequestError(f"Flow Omni 模型当前已验证最多支持 3 张参考图，当前提供了 {len(start_paths)} 张，请减少参考图数量")
            else:
                if len(start_paths) > 3:
                    raise VideoRequestError(f"Flow {task.model or 'Veo'} 模型最多支持 3 张参考图，当前提供了 {len(start_paths)} 张，请减少参考图数量")
