"""通过 gradio_client 模拟浏览器完整流程：上传视频 -> 抽帧 -> 视频去水印。"""
import sys
from PIL import Image, ImageDraw
from gradio_client import Client, handle_file

video = sys.argv[1] if len(sys.argv) > 1 else "/tmp/test_up.mp4"
client = Client("http://127.0.0.1:7860", verbose=False)

# 1. 上传视频 -> 抽取首帧（模拟上传后 change 事件）
frame = client.predict(handle_file(video), api_name="/load_video_frame")
print(f"✅ 视频上传并抽帧成功")

# 2. 构造模拟涂抹图层 -> 视频去水印
bg_path = frame["background"]
w, h = Image.open(bg_path).size
layer = "/tmp/_layer.png"
Image.new("RGBA", (w, h), (0, 0, 0, 0))
d = ImageDraw.Draw(Image.new("RGBA", (w, h), (0, 0, 0, 0)))
img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
ImageDraw.Draw(img).rectangle([w - 90, h - 60, w - 30, h - 30],
                              fill=(255, 0, 0, 255))
img.save(layer)

result = client.predict(
    handle_file(video),
    {"background": handle_file(bg_path), "layers": [handle_file(layer)],
     "composite": None, "id": None},
    6, True, 1,
    api_name="/run_video_removal")
out = result[0] if isinstance(result, (list, tuple)) else result
print(f"✅ 视频去水印完成，输出: {out}")
