"""端到端冒烟测试：图片去水印 + 视频去水印。"""
import os
import sys
import time
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mac_wm.lama_engine import pick_device, get_engine  # noqa: E402
from mac_wm.image_remover import remove_watermark  # noqa: E402
from mac_wm.video_remover import remove_video_watermark  # noqa: E402
from mac_wm.mask_utils import mask_from_boxes, overlay_preview  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test_output")
os.makedirs(OUT, exist_ok=True)

# ---- 1. 生成测试图片（带文字水印）----
img = Image.new("RGB", (960, 540), (135, 206, 235))
d = ImageDraw.Draw(img)
d.rectangle([200, 150, 760, 400], fill=(34, 139, 34))       # 草地
d.ellipse([700, 60, 880, 180], fill=(255, 215, 0))          # 太阳
try:
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 48)
except Exception:
    font = None
d.text((600, 460), "WATERMARK", fill=(255, 255, 255), font=font)  # 白色水印
img.save(f"{OUT}/input.png")

mask = mask_from_boxes([(590, 450, 900, 520)], img.size)
mask.save(f"{OUT}/mask.png")

# ---- 2. 图片去水印 ----
print(f"设备: {pick_device()}")
t0 = time.time()
engine = get_engine()
print(f"引擎加载 {time.time()-t0:.1f}s, 设备: {engine.device}")

t0 = time.time()
result = remove_watermark(img, mask, dilate_px=4, roi_mode=True)
t_img = time.time() - t0
result.save(f"{OUT}/image_result.png")
overlay_preview(img, mask).save(f"{OUT}/mask_preview.png")
print(f"图片去水印 OK ({t_img:.2f}s, {img.size})")

# 检查水印区域是否被内容替换（与纯色背景差异）
arr = np.array(result)[455:515, 600:900]
print(f"水印区域均值 RGB: {arr.reshape(-1,3).mean(0).round(1)} (原天空 135,206,235 附近为佳)")

# ---- 3. 视频去水印（3秒 30fps 小视频，固定水印）----
video_path = f"{OUT}/input.mp4"
vw = cv2.VideoWriter(video_path, cv2.VideoWriter_fourcc(*"mp4v"), 30, (640, 360))
for i in range(60):
    frame = np.full((360, 640, 3), (200, 180, 160), dtype=np.uint8)
    cv2.circle(frame, (320 + i * 2, 180), 40, (60, 60, 220), -1)   # 移动球
    cv2.putText(frame, "WM", (520, 330), cv2.FONT_HERSHEY_SIMPLEX,
                1, (255, 255, 255), 2)                              # 固定水印
    vw.write(frame)
vw.release()

t0 = time.time()
out_video = remove_video_watermark(video_path, mask_from_boxes(
    [(515, 300, 590, 335)], (640, 360)), f"{OUT}/video_result.mp4",
    dilate_px=5, workers=2, roi_mode=True)
t_vid = time.time() - t0
size = os.path.getsize(out_video)
print(f"视频去水印 OK ({t_vid:.1f}s, 输出 {size} 字节, 60帧)")

print("\n✅ 全部测试通过，输出目录:", OUT)
