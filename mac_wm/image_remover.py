"""图片去水印：单张与批量。"""

import os
import glob
from tqdm import tqdm
from PIL import Image

from .lama_engine import inpaint, inpaint_roi, get_engine, pick_device
from .mask_utils import clean_mask, dilate_mask


def remove_watermark(image: Image.Image, mask: Image.Image,
                     roi_mode: bool = True,
                     dilate_px: int = 4,
                     clean: bool = True,
                     device: str | None = None,
                     **kwargs) -> Image.Image:
    """图片去水印主入口。

    Args:
        image: 原图
        mask: 白色=水印区域
        roi_mode: 只修复 ROI 区域（速度快数倍）
        dilate_px: mask 外扩像素，覆盖水印羽化边缘
        clean: 是否清理 mask 噪点
    """
    if clean:
        mask = clean_mask(mask)
    if dilate_px > 0:
        mask = dilate_mask(mask, dilate_px)

    if roi_mode:
        return inpaint_roi(image, mask, device=device, **kwargs)
    return inpaint(image, mask, device=device, **kwargs)


def remove_watermark_file(image_path: str, mask_path: str,
                          output_path: str, **kwargs) -> str:
    """文件版：读取图片与 mask 并输出结果。"""
    image = Image.open(image_path).convert("RGB")
    mask = Image.open(mask_path).convert("L")
    result = remove_watermark(image, mask, **kwargs)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    result.save(output_path, quality=95)
    return output_path


def batch_remove(input_dir: str, mask_dir: str, output_dir: str,
                 extensions=( "*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"),
                 **kwargs) -> list[str]:
    """批量处理：目录中同名图片 + 同名 mask。

    mask 未找到的图片将跳过并警告。
    """
    os.makedirs(output_dir, exist_ok=True)
    done = []
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(input_dir, ext)))
    files = sorted(set(files))

    engine_desc = pick_device()
    print(f"设备: {engine_desc} | 共 {len(files)} 张图片")
    for path in tqdm(files, desc="图片去水印"):
        name = os.path.splitext(os.path.basename(path))[0]
        mask_path = None
        for mext in (".png", ".jpg", ".jpeg"):
            cand = os.path.join(mask_dir, name + mext)
            if os.path.exists(cand):
                mask_path = cand
                break
        if mask_path is None:
            print(f"  跳过 {name}: 未找到对应 mask")
            continue
        out = os.path.join(output_dir, name + ".png")
        remove_watermark_file(path, mask_path, out, **kwargs)
        done.append(out)
    return done


def warmup() -> str:
    """预加载模型并返回设备信息。"""
    return f"LaMa 引擎就绪，设备: {get_engine() and pick_device()}"
