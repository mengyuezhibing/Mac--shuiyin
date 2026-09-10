"""验证保存位置功能：上传图片 -> 涂抹 -> 处理 -> 文件保存到指定目录。"""
import os
import sys
from PIL import Image, ImageDraw
from gradio_client import Client, handle_file

OUT_DIR = "/tmp/macwm_save_test"
os.makedirs(OUT_DIR, exist_ok=True)

# 构造测试图片
test_img = "/tmp/save_test.png"
img = Image.new("RGB", (400, 300), (120, 180, 220))
ImageDraw.Draw(img).text((300, 250), "WM", fill=(255, 255, 255))
img.save(test_img)

# 构造涂抹层
layer = "/tmp/save_layer.png"
m = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
ImageDraw.Draw(m).rectangle([290, 240, 390, 285], fill=(255, 0, 0, 255))
m.save(layer)

client = Client("http://127.0.0.1:7860", verbose=False)
result = client.predict(
    {"background": handle_file(test_img), "layers": [handle_file(layer)],
     "composite": None, "id": None},
    4, True, True, OUT_DIR,
    api_name="/run_image_removal")
# 返回: [progress_text, out_img, preview, saved_file, saved_path_md]
flat = [r for r in result] if isinstance(result, (list, tuple)) else [result]
progress_text = flat[0]
saved = flat[3] if len(flat) > 3 else None
saved_path = flat[4] if len(flat) > 4 else None
print("进度文本:", progress_text)
print("保存信息:", str(saved_path)[:120])
print("输出目录内容:", os.listdir(OUT_DIR))
assert any(f.endswith(".png") for f in os.listdir(OUT_DIR)), "未保存到指定目录!"
print("✅ 保存位置功能验证通过")
