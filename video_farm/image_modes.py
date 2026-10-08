"""Web image routes, kept independent of the video engine and model catalogue."""
import hashlib
from pathlib import Path
from PIL import Image, UnidentifiedImageError

IMAGE_ASPECTS = ("1:1", "9:16", "3:4", "4:3", "16:9")
IMAGE_MODELS = {
    "flow": {
        "nano-pro": "Nano Banana Pro",
        "nano2-lite": "Nano Banana 2 Lite",
        "nano2.1": "Nano Banana 2.1",
    },
    "gemini": {
        "gemini-flash": "3.8 Flash",
        "gemini-flash-lite": "3.5 Flash-Lite",
        "gemini-pro": "3.1 Pro",
        "gemini-thinking": "扩展思考",
    },
}
DEFAULT_IMAGE_MODELS = {"flow": "nano-pro", "gemini": "gemini-flash"}
MAX_IMAGE_BYTES = 32 * 1024 * 1024


def image_options():
    return {
        "engines": [
            {"id": "flow", "label": "Google Flow 网页生图", "model_label": "图像生成模型"},
            {"id": "gemini", "label": "Gemini 网页生图", "model_label": "Gemini 网页模式"},
        ],
        "models": {engine: [{"id": key, "label": label} for key, label in models.items()]
                   for engine, models in IMAGE_MODELS.items()},
        "default_models": DEFAULT_IMAGE_MODELS,
        "aspect_ratios": list(IMAGE_ASPECTS),
        "availability_note": "以所选账号网页提供的选项为准；不可用时明确报错，不自动换模型。",
    }


def validate_image_settings(engine, model, aspect_ratio):
    engine = (engine or "flow").strip().lower()
    if engine not in IMAGE_MODELS:
        raise ValueError("生图只支持 Google Flow 和 Gemini 网页通道")
    model = (model or DEFAULT_IMAGE_MODELS[engine]).strip()
    if model not in IMAGE_MODELS[engine]:
        raise ValueError(f"{engine} 不支持生图型号 {model}；请重新选择网页提供的模型/模式")
    if aspect_ratio not in IMAGE_ASPECTS:
        raise ValueError("不支持该生图画幅，请选择 1:1、9:16、3:4、4:3 或 16:9")
    return engine, model, aspect_ratio


def validate_image_file(path, aspect_ratio=None, *, generated=False):
    """Require a real decodable image, never an HTML/error download."""
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_IMAGE_BYTES:
        raise ValueError("图片不存在、为空或超过 32MB")
    try:
        with Image.open(path) as image:
            width, height = image.size
            if min(width, height) < 32:
                raise ValueError("图片尺寸过小")
            if generated and (min(width, height) < 512 or max(width, height) < 1024):
                raise ValueError("图片分辨率不足，可能下载的是缩略图而非原始尺寸产物")
            image.verify()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError("文件不是可解码图片") from exc
    if aspect_ratio:
        left, right = map(int, aspect_ratio.split(":"))
        if abs(width / height / (left / right) - 1) > 0.035:
            raise ValueError(f"生成图片为 {width}×{height}，不符合所选 {aspect_ratio} 画幅")
    return width, height


def validate_image_result(result, task, output_root):
    """Accept only files from this task's unique attempt, never old gallery images."""
    _, _, aspect = validate_image_settings(task.engine, task.model, task.aspect_ratio)
    directory = Path(result.get("attempt_dir") or "").resolve()
    task_root = (Path(output_root).resolve() / task.id).resolve()
    if directory.parent != task_root or not directory.name.startswith("attempt_"):
        raise ValueError("未提供本任务本次生成的独立结果目录")
    paths = result.get("output_image_paths")
    if not isinstance(paths, list) or not paths:
        raise ValueError("执行器没有返回本次生成的图片")
    reference = Path(task.start_image_path) if task.start_image_path else None
    input_digest = hashlib.sha256(reference.read_bytes()).digest() if reference and reference.is_file() else None
    for image_path in paths:
        target = Path(image_path).resolve()
        if not target.is_relative_to(directory):
            raise ValueError("执行器返回了其他任务或其他生成批次的图片")
        validate_image_file(target, aspect, generated=True)
        if input_digest is not None and hashlib.sha256(target.read_bytes()).digest() == input_digest:
            raise ValueError("下载产物与输入参考图完全相同，不能认作新生成图片")
    return paths
