"""LaMa 修复引擎（自包含实现，不依赖 simple-lama-inpainting）。

- 直接加载 big-lama TorchScript 权重（约 200MB，首次自动下载，多源回退）
- 自动选择设备：Apple Silicon MPS -> CPU（运行失败自动永久回退）
- 权重来源: enesmsahin/simple-lama-inpainting 与 Sanster/IOPaint 发布的 big-lama
"""

import os
import sys
import warnings
import urllib.request
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

ENGINE = None
ENGINE_DEVICE = None
FALLBACK_DONE = False

# big-lama 权重下载源（按顺序尝试，含国内镜像）
MODEL_URLS = [
    "https://hf-mirror.com/Sanster/big-lama/resolve/main/big-lama.pt",
    "https://huggingface.co/Sanster/big-lama/resolve/main/big-lama.pt",
    "https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt",
]


def model_path() -> str:
    """权重缓存路径：项目内 models/ 优先，其次 ~/.cache/mac_wm/。"""
    local = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "models", "big-lama.pt")
    if os.path.exists(local):
        return local
    cache = os.path.join(os.path.expanduser("~"), ".cache", "mac_wm",
                         "big-lama.pt")
    return cache if os.path.exists(cache) else local


def download_model(progress=True) -> str:
    """下载 big-lama 权重（带多源回退）。"""
    dst = model_path()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    last_err = None
    for url in MODEL_URLS:
        try:
            if progress:
                print(f"下载 LaMa 模型: {url}")
                # urllib 无断点续传，简单实现进度回调
                req = urllib.request.Request(url, headers={"User-Agent": "mac-wm"})
                with urllib.request.urlopen(req) as resp, \
                        open(dst + ".part", "wb") as f:
                    total = int(resp.headers.get("Content-Length", 0) or 0)
                    done = 0
                    while True:
                        chunk = resp.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if total and progress:
                            pct = done * 100 // total
                            sys.stdout.write(f"\r  {pct:3d}% "
                                             f"({done >> 20}MB/{total >> 20}MB)")
                            sys.stdout.flush()
                if progress:
                    print()
            else:
                urllib.request.urlretrieve(url, dst + ".part")
            os.replace(dst + ".part", dst)
            return dst
        except Exception as e:
            last_err = e
            print(f"  源失败: {e}", file=sys.stderr)
    raise RuntimeError(f"模型下载失败，请手动下载 big-lama.pt 到 {dst}\n"
                       f"最后错误: {last_err}")


def pick_device() -> str:
    """选择可用推理设备：MPS 优先，其次 CPU。"""
    if torch.backends.mps.is_available():
        try:
            _ = torch.zeros(1, device="mps") * 2
            return "mps"
        except Exception:
            pass
    return "cpu"


class LamaEngine:
    """big-lama TorchScript 推理封装。"""

    def __init__(self, device: str):
        path = model_path()
        if not os.path.exists(path):
            path = download_model()
        self.device = device
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=FutureWarning)
            self.model = torch.jit.load(path, map_location=device)
        self.model.eval()

    def __call__(self, image: Image.Image, mask: Image.Image) -> Image.Image:
        img = np.array(image.convert("RGB")).astype(np.float32) / 255.0
        m = (np.array(mask.convert("L")) > 60).astype(np.float32)

        img_t = torch.from_numpy(img).permute(2, 0, 1).unsqueeze(0)
        mask_t = torch.from_numpy(m).unsqueeze(0).unsqueeze(0)

        # LaMa 要求尺寸为 8 的倍数：reflect pad 图像 / zero pad mask
        h, w = img_t.shape[-2:]
        ph, pw = (8 - h % 8) % 8, (8 - w % 8) % 8
        if ph or pw:
            img_t = F.pad(img_t, (0, pw, 0, ph), mode="reflect")
            mask_t = F.pad(mask_t, (0, pw, 0, ph), mode="constant", value=0)

        with torch.no_grad():
            out = self.model(img_t.to(self.device), mask_t.to(self.device))

        out = out.clamp(0, 1)[0].cpu().numpy().transpose(1, 2, 0)
        out = (out[:h, :w] * 255.0).round().astype(np.uint8)
        return Image.fromarray(out)


def get_engine(device: str | None = None) -> LamaEngine:
    """获取全局引擎单例；MPS 推理失败时自动回退 CPU 重建。"""
    global ENGINE, ENGINE_DEVICE, FALLBACK_DONE
    if ENGINE is not None and (device is None or device == ENGINE_DEVICE):
        return ENGINE

    dev = device or pick_device()
    ENGINE = LamaEngine(dev)
    ENGINE_DEVICE = dev
    FALLBACK_DONE = False
    return ENGINE


def _rebuild_on_cpu() -> LamaEngine:
    global ENGINE, ENGINE_DEVICE, FALLBACK_DONE
    ENGINE = LamaEngine("cpu")
    ENGINE_DEVICE = "cpu"
    FALLBACK_DONE = True
    print("已回退到 CPU 推理", file=sys.stderr)
    return ENGINE


def inpaint(image: Image.Image, mask: Image.Image,
            device: str | None = None) -> Image.Image:
    """对图像执行 LaMa 修复（mask 白色=水印区域）。"""
    engine = get_engine(device)
    try:
        return engine(image, mask)
    except RuntimeError as e:
        # MPS 不支持部分算子（如 FFT）时自动回退 CPU
        msg = str(e).lower()
        if engine.device != "cpu" and not FALLBACK_DONE and \
                ("mps" in msg or "metal" in msg or "not implemented" in msg):
            _rebuild_on_cpu()
            return ENGINE(image, mask)
        raise


def inpaint_roi(image: Image.Image, mask: Image.Image,
                padding: int = 32, device: str | None = None) -> Image.Image:
    """仅对水印周边 ROI 执行修复后贴回（大幅提速，效果几乎一致）。"""
    mask_arr = np.array(mask.convert("L"))
    ys, xs = np.where(mask_arr > 10)
    if len(xs) == 0:
        return image  # 空 mask，无需处理

    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    w, h = image.size
    x0 = max(0, x0 - padding)
    y0 = max(0, y0 - padding)
    x1 = min(w, x1 + padding)
    y1 = min(h, y1 + padding)

    roi_img = image.crop((x0, y0, x1, y1))
    roi_mask = mask.crop((x0, y0, x1, y1))

    result_roi = inpaint(roi_img, roi_mask, device=device)
    result = image.copy()
    result.paste(result_roi, (x0, y0))
    return result
