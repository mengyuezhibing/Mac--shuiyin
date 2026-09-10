#!/bin/bash
# Mac 一键安装脚本（Intel / Apple Silicon 通用）
set -e
cd "$(dirname "$0")"

echo "==> [1/4] 视频音频处理说明"
echo "   视频去水印后的音频合成使用内置 ffmpeg（imageio-ffmpeg 自带二进制），"
echo "   无需单独安装系统 ffmpeg，打包后的 .app 也能正常保留音频。"

echo "==> [2/4] 创建 Python 虚拟环境 (venv)"
PYTHON=${PYTHON:-python3}
$PYTHON -m venv .venv
source .venv/bin/activate

echo "==> [3/4] 升级 pip 并安装依赖（含 PyTorch，约 2GB，请耐心等待）"
pip install --upgrade pip
pip install -r requirements.txt

echo "==> [4/4] 验证"
python - <<'EOF'
import torch
from mac_wm.lama_engine import pick_device
print(f"PyTorch {torch.__version__} | 推理设备: {pick_device()}")
EOF

echo ""
echo "✅ 安装完成！启动方式："
echo "   1. 双击 run.command（图形界面）"
echo "   2. 或终端执行: source .venv/bin/activate && python cli.py server"
