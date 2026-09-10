"""Mask 处理工具：生成、清理、可视化。"""

import cv2
import numpy as np
from PIL import Image


def mask_from_boxes(boxes, size: tuple[int, int]) -> Image.Image:
    """根据矩形框列表生成 mask。

    Args:
        boxes: [(x1, y1, x2, y2), ...] 像素坐标
        size: (width, height)
    """
    m = np.zeros((size[1], size[0]), dtype=np.uint8)
    for (x1, y1, x2, y2) in boxes:
        cv2.rectangle(m, (int(x1), int(y1)), (int(x2), int(y2)), 255, -1)
    return Image.fromarray(m)


def mask_from_points(points, size: tuple[int, int],
                     radius: int = 12) -> Image.Image:
    """根据点击点列表生成圆形 mask（适合 logo 类点选）。"""
    m = np.zeros((size[1], size[0]), dtype=np.uint8)
    for (x, y) in points:
        cv2.circle(m, (int(x), int(y)), int(radius), 255, -1)
    return Image.fromarray(m)


def clean_mask(mask: Image.Image, kernel_size: int = 5,
               min_area: int = 64) -> Image.Image:
    """清理 mask：闭运算填补小孔 + 去除过小的噪点区域。"""
    arr = np.array(mask.convert("L"))
    _, binary = cv2.threshold(arr, 60, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    if min_area > 0:
        num, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
        for i in range(1, num):
            if stats[i, cv2.CC_STAT_AREA] < min_area:
                binary[labels == i] = 0
    return Image.fromarray(binary)


def dilate_mask(mask: Image.Image, pixels: int = 4) -> Image.Image:
    """扩展 mask 边缘，覆盖水印抗锯齿边缘，去除更干净。"""
    arr = np.array(mask.convert("L"))
    if pixels <= 0:
        return mask
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (pixels * 2 + 1, pixels * 2 + 1))
    arr = cv2.dilate(arr, kernel)
    return Image.fromarray(arr)


def auto_mask_by_color(image: Image.Image, seed_points,
                       tolerance: int = 40,
                       region: tuple | None = None) -> Image.Image:
    """按颜色相似度自动生成 mask（半透明/纯色水印适用）。

    Args:
        seed_points: [(x, y), ...] 用户在水印上点击的取样点
        tolerance: 颜色容差（0-255）
        region: (x1, y1, x2, y2) 限制检测区域，None 为全图
    """
    img = np.array(image.convert("RGB")).astype(np.int16)
    h, w = img.shape[:2]
    m = np.zeros((h, w), dtype=np.uint8)

    # 区域限制
    area = np.zeros((h, w), dtype=bool)
    if region:
        x1, y1, x2, y2 = [int(v) for v in region]
        area[max(0, y1):min(h, y2), max(0, x1):min(w, x2)] = True
    else:
        area[:] = True

    seeds = [img[int(y), int(x)] for (x, y) in seed_points]
    dists = np.full((h, w), 1e9, dtype=np.float32)
    for s in seeds:
        d = np.sqrt(((img - s.reshape(1, 1, 3)) ** 2).sum(axis=2))
        dists = np.minimum(dists, d)

    m[(dists <= tolerance) & area] = 255
    return Image.fromarray(m)


def overlay_preview(image: Image.Image, mask: Image.Image,
                    color=(255, 0, 0), alpha: float = 0.45) -> Image.Image:
    """生成 mask 叠加预览图（红色半透明标出水印区域）。"""
    base = np.array(image.convert("RGB")).astype(np.float32)
    m = np.array(mask.convert("L")) > 60
    layer = base.copy()
    layer[m] = np.array(color, dtype=np.float32)
    out = base * (1 - alpha) + layer * alpha
    return Image.fromarray(out.astype(np.uint8))
