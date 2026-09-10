"""Gradio Web UI：图片去水印 + 视频去水印（实时进度 / 自定义保存位置）。"""

import os
import re
import sys
import time
import shutil
import tempfile
import threading
import subprocess
import numpy as np
import gradio as gr
from PIL import Image

from .image_remover import remove_watermark
from .video_remover import remove_video_watermark, extract_preview_frame
from .mask_utils import overlay_preview

DEFAULT_OUT_DIR = os.path.join(os.path.expanduser("~"), "Downloads")


def _editor_to_mask(editor_value, size: tuple[int, int]) -> Image.Image | None:
    """从 Gradio ImageEditor 输出提取涂抹层为 mask。"""
    if not editor_value:
        return None
    layers = editor_value.get("layers") or []
    w, h = size
    mask = None
    for layer in layers:
        if layer is None:
            continue
        arr = np.array(layer.convert("RGBA"))
        alpha = arr[..., 3]
        if (alpha > 30).sum() == 0:
            continue
        m = np.zeros((h, w), dtype=np.uint8)
        m[alpha > 30] = 255
        candidate = Image.fromarray(m)
        mask = candidate if mask is None else Image.fromarray(
            np.maximum(np.array(mask), m))
    if mask is None:
        return None
    if mask.size != size:
        mask = mask.resize(size, Image.NEAREST)
    return mask


def _file_path(value):
    """从 gr.File 输入提取本地路径（兼容 str / dict / FileData）。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("path") or value.get("name")
    return getattr(value, "path", None)


def _save_dir(out_dir: str) -> str:
    """校验/创建输出目录。"""
    out_dir = (out_dir or "").strip() or DEFAULT_OUT_DIR
    out_dir = os.path.abspath(os.path.expanduser(out_dir))
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _save_output(src_path: str, out_dir: str, suffix: str = "无水印") -> str:
    """把结果保存到用户目录（同名自动加时间戳）。"""
    out_dir = _save_dir(out_dir)
    base = os.path.splitext(os.path.basename(src_path))[0]
    base = re.sub(r"[\\/:*?\"<>|]", "_", base) or "output"
    dst = os.path.join(out_dir, f"{base}_{suffix}.png")
    n = 1
    while os.path.exists(dst):
        dst = os.path.join(out_dir, f"{base}_{suffix}_{n}.png")
        n += 1
    shutil.copy(src_path, dst)
    return dst


def _save_output_video(src_path: str, out_dir: str, suffix: str = "无水印") -> str:
    out_dir = _save_dir(out_dir)
    base = os.path.splitext(os.path.basename(src_path))[0]
    base = re.sub(r"[\\/:*?\"<>|]", "_", base) or "output"
    dst = os.path.join(out_dir, f"{base}_{suffix}.mp4")
    n = 1
    while os.path.exists(dst):
        dst = os.path.join(out_dir, f"{base}_{suffix}_{n}.mp4")
        n += 1
    shutil.copy(src_path, dst)
    return dst


def choose_folder():
    """弹出 macOS 原生文件夹选择器（AppleScript）。"""
    script = ('POSIX path of (choose folder with prompt '
              '"选择去水印结果的保存位置")')
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=120)
        path = r.stdout.strip()
        if r.returncode == 0 and path:
            return path
    except Exception:
        pass
    return gr.update()  # 用户取消则保持不变


def reveal_in_finder(path: str):
    """在 Finder 中显示文件/文件夹。"""
    if path and os.path.exists(path):
        # AppleScript 字符串必须用双引号，且需转义路径中的特殊字符
        esc = path.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.Popen(["osascript", "-e",
                          f'tell application "Finder" to reveal '
                          f'(POSIX file "{esc}")',
                          "-e", 'tell application "Finder" to activate'])


def _progress_text(done: int, total: int, stage: str) -> str:
    if total:
        return f"{stage}：{done * 100 // total}%（{done}/{total}）"
    return f"{stage}：{done}"


def open_save_folder(dir_text: str):
    """在 Finder 中打开保存目录（顶部『打开文件夹』按钮）。"""
    reveal_in_finder(_save_dir(dir_text))


def reveal_saved_file(path: str):
    """在 Finder 中显示已保存的文件（各 Tab『在 Finder 中显示』按钮）。"""
    reveal_in_finder(path)


# ---------------- 图片 Tab ----------------

def run_image_removal(editor_value, dilate_px, roi_mode, clean_mask_on,
                      out_dir, progress=gr.Progress()):
    """图片去水印（generator 模式，实时进度）。"""
    if not editor_value or editor_value.get("background") is None:
        raise gr.Error("请先上传图片并涂抹水印区域")
    bg = editor_value["background"]
    if isinstance(bg, np.ndarray):
        bg = Image.fromarray(bg)
    image = bg.convert("RGB")
    mask = _editor_to_mask(editor_value, image.size)
    if mask is None:
        raise gr.Error("请用画笔涂抹水印区域后再开始")

    yield (gr.update(value="正在加载 LaMa 模型…"), gr.update(), gr.update(),
           gr.update(), gr.update())

    result_holder = {}
    def worker():
        try:
            result_holder["result"] = remove_watermark(
                image, mask, roi_mode=bool(roi_mode),
                dilate_px=int(dilate_px), clean=bool(clean_mask_on))
        except Exception as e:
            result_holder["error"] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    while t.is_alive():
        progress(0.5, desc="正在 AI 修复…")
        t.join(timeout=0.2)
    if "error" in result_holder:
        raise gr.Error(f"处理失败: {result_holder['error']}")

    progress(0.85, desc="正在保存…")
    out_dir_ok = _save_dir(out_dir)
    tmp_png = os.path.join(tempfile.mkdtemp(prefix="macwm_img_"), "result.png")
    result_holder["result"].save(tmp_png, quality=95)
    saved = _save_output(tmp_png, out_dir)

    progress(1.0, desc="完成")
    preview = overlay_preview(image, mask)
    yield (gr.update(value="✅ 完成"), result_holder["result"], preview,
           gr.update(value=f"✅ 已保存到: `{saved}`", visible=True),
           gr.update(value=saved))


def load_video_frame(video_path):
    """上传视频后自动抽取第一帧供标注。"""
    path = _file_path(video_path)
    if not path:
        raise gr.Error("请先上传视频")
    try:
        return extract_preview_frame(path, index=0)
    except Exception as e:
        raise gr.Error(f"无法读取该视频（OpenCV 不支持此编码）: {e}")


def run_video_removal(video_path, editor_value, dilate_px, roi_mode,
                      workers, out_dir, progress=gr.Progress()):
    """视频去水印（generator 模式，逐帧实时进度）。"""
    video_path = _file_path(video_path)
    if not video_path:
        raise gr.Error("请先上传视频")
    if not editor_value or editor_value.get("background") is None:
        raise gr.Error("请先点击『抽取帧预览』并涂抹水印区域")
    bg = editor_value["background"]
    if isinstance(bg, np.ndarray):
        bg = Image.fromarray(bg)
    frame = bg.convert("RGB")
    mask = _editor_to_mask(editor_value, frame.size)
    if mask is None:
        raise gr.Error("请用画笔涂抹水印区域后再开始")

    state = {"done": 0, "total": 0, "stage": "准备中"}
    result_holder = {}

    def worker():
        out = os.path.join(tempfile.mkdtemp(prefix="macwm_out_"),
                           "result.mp4")
        try:
            result_holder["result"] = remove_video_watermark(
                video_path, mask, out,
                dilate_px=int(dilate_px), workers=int(workers),
                roi_mode=bool(roi_mode),
                progress_callback=lambda d, t, s: state.update(
                    done=d, total=t, stage=s))
        except Exception as e:
            result_holder["error"] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    last_text = ""
    while t.is_alive():
        text = _progress_text(state["done"], state["total"], state["stage"])
        if text != last_text:
            progress((state["done"] / state["total"]) if state["total"] else 0,
                     desc=state["stage"])
            last_text = text
        t.join(timeout=0.2)
    if "error" in result_holder:
        raise gr.Error(f"处理失败: {result_holder['error']}")

    progress(0.95, desc="正在保存到指定目录…")
    saved = _save_output_video(result_holder["result"], out_dir)
    progress(1.0, desc="完成")

    preview = overlay_preview(frame, mask)
    yield (gr.update(value="✅ 完成"), result_holder["result"], preview,
           gr.update(value=f"✅ 已保存到: `{saved}`", visible=True),
           gr.update(value=saved))


# ---------------- UI ----------------

def build_ui() -> gr.Blocks:
    ui = gr.Blocks(title="Mac 水印去除")
    with ui:
        gr.Markdown(
            "# 🧹 Mac 图片与视频水印去除\n"
            "基于 **LaMa** AI 修复模型（整合 IOPaint / WatermarkRemover-AI / "
            "ProPainter 思路）· 支持苹果芯片 MPS 加速\n\n"
            "**用法**：上传文件 → 用画笔涂抹水印 → 点击开始 → 在 Finder 查看")
        # ---- 公共保存位置 ----
        with gr.Row(equal_height=True):
            out_dir_box = gr.Textbox(value=DEFAULT_OUT_DIR,
                                     label="保存位置（文件夹）",
                                     scale=4, interactive=True)
            btn_browse = gr.Button("📁 浏览…", scale=1, variant="secondary")
            btn_reveal = gr.Button("📂 打开文件夹", scale=1,
                                   variant="secondary")
        btn_browse.click(choose_folder, None, [out_dir_box])
        btn_reveal.click(open_save_folder, [out_dir_box], None)

        with gr.Tabs():
            # ---- 图片 ----
            with gr.Tab("🖼 图片去水印"):
                progress_img = gr.Textbox(label="处理进度", interactive=False,
                                          value="等待任务")
                with gr.Row():
                    with gr.Column():
                        img_editor = gr.ImageEditor(
                            label="上传图片并涂抹水印（可画笔擦除）",
                            type="pil", brush=gr.Brush(colors=["#ff0000"]),
                            eraser=True, layers=False, height=420)
                        with gr.Row():
                            dilate_img = gr.Slider(0, 15, 4, step=1,
                                                   label="边缘扩展(px)")
                            roi_img = gr.Checkbox(True, label="ROI 加速")
                            clean_img = gr.Checkbox(True, label="清理噪点")
                        btn_img = gr.Button("🚀 开始去水印", variant="primary")
                    with gr.Column():
                        out_img = gr.Image(label="结果", type="pil", height=380)
                        out_mask = gr.Image(label="水印区域(红色预览)",
                                            type="pil", height=180)
                        saved_state_img = gr.State(None)
                        saved_md_img = gr.Markdown(visible=False)
                        gr.Button("📂 在 Finder 中显示").click(
                            reveal_saved_file, [saved_state_img], None)
                btn_img.click(
                    run_image_removal,
                    [img_editor, dilate_img, roi_img, clean_img, out_dir_box],
                    [progress_img, out_img, out_mask, saved_md_img,
                     saved_state_img])

            # ---- 视频 ----
            with gr.Tab("🎬 视频去水印"):
                gr.Markdown("支持 mp4 / mov / mkv / avi / webm 等任意常见格式"
                            "（静态固定位置水印效果最佳）")
                video_in = gr.File(label="上传视频文件",
                                   file_types=[".mp4", ".mov", ".mkv",
                                               ".avi", ".webm", ".m4v",
                                               ".mpg", ".mpeg", ".ts",
                                               ".flv", ".wmv", ".3gp"])
                progress_vid = gr.Textbox(label="处理进度", interactive=False,
                                          value="等待任务")
                with gr.Row():
                    with gr.Column():
                        vid_editor = gr.ImageEditor(
                            label="在抽出的帧上涂抹水印位置",
                            type="pil", brush=gr.Brush(colors=["#ff0000"]),
                            eraser=True, layers=False, height=380)
                        btn_frame = gr.Button("📷 重新抽取帧预览")
                        with gr.Row():
                            dilate_vid = gr.Slider(0, 20, 6, step=1,
                                                   label="边缘扩展(px)")
                            roi_vid = gr.Checkbox(True, label="ROI 加速")
                            workers_vid = gr.Slider(1, 4, 2, step=1,
                                                    label="并行线程")
                        btn_vid = gr.Button("🚀 开始处理视频",
                                            variant="primary")
                    with gr.Column():
                        out_vid = gr.Video(label="结果视频")
                        out_vid_mask = gr.Image(label="水印区域(红色预览)",
                                                type="pil", height=180)
                        saved_state_vid = gr.State(None)
                        saved_md_vid = gr.Markdown(visible=False)
                        gr.Button("📂 在 Finder 中显示").click(
                            reveal_saved_file, [saved_state_vid], None)
                video_in.change(load_video_frame, [video_in], [vid_editor],
                                show_progress="hidden")
                btn_frame.click(load_video_frame, [video_in], [vid_editor])
                btn_vid.click(
                    run_video_removal,
                    [video_in, vid_editor, dilate_vid, roi_vid, workers_vid,
                     out_dir_box],
                    [progress_vid, out_vid, out_vid_mask, saved_md_vid,
                     saved_state_vid])

            # ---- 帮助 ----
            with gr.Tab("⌨️ 命令行用法"):
                gr.Markdown(
                    "### 命令行批量处理\n"
                    "```bash\n"
                    "# 图片（mask：白色=水印）\n"
                    "python cli.py image -i 输入.jpg -m 水印mask.png -o 输出.png\n\n"
                    "# 批量（目录下同名 图片/mask 配对）\n"
                    "python cli.py batch -d 图片目录 -m mask目录 -o 输出目录\n\n"
                    "# 视频（直接给水印框 x1,y1,x2,y2）\n"
                    "python cli.py video -i 输入.mp4 -b 1180,60,1860,130 -o 输出.mp4\n"
                    "```")

            # ---- 退出 ----
            with gr.Tab("⏻ 退出"):
                gr.Markdown("点击下方按钮将完全退出本应用。")
                gr.Button("退出应用", variant="stop").click(
                    lambda: os._exit(0))
    return ui


def main():
    import socket
    import webbrowser
    # 端口已被占用说明应用已在运行：直接打开浏览器并退出新进程
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 7860))
    except OSError:
        webbrowser.open("http://127.0.0.1:7860")
        sys.exit(0)
    finally:
        sock.close()

    build_ui().queue().launch(server_name="127.0.0.1", server_port=7860,
                              show_error=True, inbrowser=True,
                              css=".container{max-width:1080px;margin:auto}")


if __name__ == "__main__":
    main()
