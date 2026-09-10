"""视频去水印：ffmpeg 提帧 -> LaMa 逐帧修复 -> ffmpeg 合成（保留音频）。

流程整合自 video-watermark-removal 与 ProPainter 的工程实践，
针对 Mac 优化：ROI 加速、多进程帧修复、自动 ffmpeg 检测。
"""

import os
import sys
import shutil
import tempfile
import subprocess
import functools
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import cv2
import numpy as np
from PIL import Image

from .image_remover import remove_watermark
from .mask_utils import clean_mask, dilate_mask


@functools.lru_cache(maxsize=1)
def _ffmpeg_exe() -> str | None:
    """获取可用的 ffmpeg 可执行文件路径。

    优先使用 imageio-ffmpeg 自带的独立二进制（无需用户系统安装 ffmpeg，
    打包后的 .app 也能正常工作）；否则回退到系统 PATH 中的 ffmpeg。
    """
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    return shutil.which("ffmpeg")


def ffmpeg_available() -> bool:
    return _ffmpeg_exe() is not None


def _probe_fps(path: str) -> float:
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    return fps if fps and fps > 0 else 30.0


def _fix_frame(args):
    """工作线程：修复单帧（线程池内共享 LaMa 引擎，PyTorch 线程安全）。"""
    frame_bgr, mask_pil, kwargs = args
    frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(frame)
    try:
        result = remove_watermark(image, mask_pil, **kwargs)
        return cv2.cvtColor(np.array(result), cv2.COLOR_RGB2BGR)
    except Exception as e:
        print(f"\n帧修复失败: {e}", file=sys.stderr)
        return frame_bgr


def remove_video_watermark(video_path: str, mask: Image.Image,
                           output_path: str,
                           dilate_px: int = 5,
                           workers: int = 2,
                           preview_every: int = 0,
                           keep_audio: bool = True,
                           tmp_dir: str | None = None,
                           progress_callback=None,
                           **kwargs) -> str:
    """视频去水印主入口。

    Args:
        video_path: 输入视频
        mask: 静态水印 mask（视频水印通常位置固定）
        output_path: 输出 mp4
        dilate_px: mask 外扩（视频压缩会产生扩散边，稍大更干净）
        workers: 并行修复线程数（MPS/CPU 推理本身串行，多线程仅覆盖 IO）
        keep_audio: 保留原音频（需 ffmpeg）
        progress_callback: 进度回调 callback(done, total, stage)
    Returns:
        输出文件路径
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(video_path)

    mask = dilate_mask(clean_mask(mask), dilate_px)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频: {video_path}")
    fps = _probe_fps(video_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    workdir = tmp_dir or tempfile.mkdtemp(prefix="macwm_")
    os.makedirs(workdir, exist_ok=True)
    silent_mp4 = os.path.join(workdir, "silent.mp4")

    writer = cv2.VideoWriter(silent_mp4, cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, (width, height))

    def gen_frames():
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            yield frame
        cap.release()

    frames = gen_frames()
    pbar = tqdm(total=total or None, desc="视频逐帧修复", unit="帧")
    done = 0
    if progress_callback:
        progress_callback(0, total or 0, "正在逐帧修复水印")

    def run_pool():
        # 分批读取 -> 并行修复 -> 写入（避免一次性载入全部帧爆内存）
        nonlocal done
        BATCH = max(workers * 2, 4)
        while True:
            batch = []
            for _ in range(BATCH):
                try:
                    frame = next(frames)
                except StopIteration:
                    break
                batch.append((frame, mask, kwargs))
            if not batch:
                break
            if workers > 1:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    results = list(pool.map(_fix_frame, batch))
            else:
                results = [_fix_frame(b) for b in batch]
            for r in results:
                writer.write(r)
            pbar.update(len(batch))
            done += len(batch)
            if progress_callback:
                progress_callback(done, total or 0, "正在逐帧修复水印")

    try:
        run_pool()
    finally:
        writer.release()
        pbar.close()

    # ---- 音频合成 ----
    if progress_callback:
        progress_callback(total or done, total or done, "正在编码合成音频")
    exe = _ffmpeg_exe()
    if exe and keep_audio:
        cmd = [exe, "-y", "-loglevel", "error",
               "-i", silent_mp4, "-i", video_path,
               "-map", "0:v:0", "-map", "1:a?",
               "-c:v", "libx264", "-preset", "medium", "-crf", "20",
               "-c:a", "aac", "-b:a", "192k",
               "-movflags", "+faststart",
               output_path]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"\n音频合成失败，回退为无声输出: {e}", file=sys.stderr)
            shutil.copy(silent_mp4, output_path)
    else:
        shutil.copy(silent_mp4, output_path)
        if keep_audio and not exe:
            print("警告: 未检测到 ffmpeg，输出无音频。", file=sys.stderr)

    # 清理临时目录
    if tmp_dir is None:
        shutil.rmtree(workdir, ignore_errors=True)
    return output_path


def extract_preview_frame(video_path: str, index: int = 0) -> Image.Image:
    """抽取视频某帧用于标注水印区域。"""
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, index))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError("抽帧失败")
    return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
