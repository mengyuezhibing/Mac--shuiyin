#!/bin/bash
# 双击启动图形界面
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "首次运行：正在安装环境（需要几分钟）..."
  bash setup_mac.sh
fi

source .venv/bin/activate
python cli.py server
