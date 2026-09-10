# 🧹 Mac 图片与视频水印去除工具

整合以下 GitHub 开源项目核心能力，重写为 **macOS 原生友好版**（支持 Apple Silicon MPS 加速）：

| 来源项目 | 借鉴内容 |
|---------|---------|
| [Sanster/IOPaint](https://github.com/Sanster/IOPaint)（原 Lama Cleaner） | LaMa 修复模型、批量处理思路 |
| [D-Ogi/WatermarkRemover-AI](https://github.com/D-Ogi/WatermarkRemover-AI) | "检测区域 → 修复" 交互流程 |
| [sczhou/ProPainter](https://github.com/sczhou/ProPainter) / video-watermark-removal | 视频逐帧修复 + ffmpeg 工程流程 |

相比直接使用原项目，本工具做了 Mac 适配与整合：

- ✅ **单一 LaMa 引擎**同时服务图片与视频（原视频方案依赖重型 ProPainter，Mac 内存压力大）
- ✅ **Apple Silicon MPS 自动加速**，失败自动回退 CPU
- ✅ **ROI 局部修复**：只计算水印周边区域，速度提升数倍
- ✅ **Web 界面涂抹标注** + 命令行批量处理两种用法
- ✅ 视频自动保留音频（ffmpeg），无 ffmpeg 时优雅降级

## 从 GitHub 获取

```bash
git clone https://github.com/mengyuezhibing/MacWatermarkRemover.git
cd MacWatermarkRemover
bash setup_mac.sh    # 安装依赖（含 PyTorch，约 2GB，请耐心等待）
bash make_app.sh     # 生成带图标的 MacWatermarkRemover.app
```

之后按下方「快速开始」使用。LaMa 模型权重（约 200MB）首次运行会自动下载，国内网络慢时可先运行 `bash download_model.sh`。

## 快速开始

### 方式一：Mac App（推荐）

```bash
bash setup_mac.sh          # 首次安装环境
bash make_app.sh           # 构建 MacWatermarkRemover.app（含自定义图标）
open MacWatermarkRemover.app
```

双击 `MacWatermarkRemover.app` 会打开**独立的原生窗口**（WKWebView，不依赖浏览器）：
- 顶部设置保存位置（可点「浏览…」弹出 Mac 原生文件夹选择器）
- 图片/视频处理均有实时进度条；完成后可点「📂 在 Finder 中显示」直达文件
- 重复双击不会重复启动；关闭窗口即退出应用
- 运行日志：项目根目录 `app.log`

### 方式二：命令行

```bash
source .venv/bin/activate
python cli.py server        # Web 界面
# 浏览器自动打开 http://127.0.0.1:7860
```

首次运行会自动下载 LaMa 模型（约 200MB）。国内网络缓慢时可先运行
`bash download_model.sh`（自动检测本地代理 7897/7890/1087/1080 分块下载），或将
`big-lama.pt` 手动放入 `models/` 目录。

> 模型权重来源: [simple-lama-inpainting releases](https://github.com/enesmsahin/simple-lama-inpainting/releases)（big-lama TorchScript）

### 换图标

```bash
bash make_app.sh /path/to/你的图片.jpg
```

## 视频格式说明

视频上传组件接受**任意常见格式**（mp4/mov/mkv/avi/webm/m4v/mpg/ts/flv/wmv/3gp），
上传后自动抽取首帧用于标注。浏览器本身无法预览的格式（如 avi/wmv）不影响处理，
处理结果统一输出为 H.264 mp4。

## 图形界面用法

1. **图片**：上传 → 用画笔涂抹水印 → 开始去水印
2. **视频**：上传 → 点"抽取帧预览" → 涂抹水印位置（静态水印）→ 开始处理
3. 红色预览图可检查水印覆盖范围；"边缘扩展"建议 4-8px 覆盖羽化边缘

## 命令行用法

```bash
source .venv/bin/activate

# 图片：mask 图（白色=水印区域）
python cli.py image -i 照片.jpg -m mask.png -o 结果.png

# 图片：直接给坐标框 x1,y1,x2,y2
python cli.py image -i 照片.jpg -b "100,80,420,160" -o 结果.png

# 批量：目录中同名 图片.xxx 与 mask.png 配对
python cli.py batch -d 图片目录 -m mask目录 -o 输出目录

# 视频：水印位置固定时给坐标框
python cli.py video -i 视频.mp4 -b "1180,60,1860,130" -o 结果.mp4
```

## 常用参数

| 参数 | 默认 | 说明 |
|------|-----|------|
| `--dilate` | 4(图)/6(视频) | mask 外扩像素，水印有羽化边时调大 |
| `--no-roi` | - | 关闭 ROI 加速（全图修复） |
| `--workers` | 2 | 视频处理并行线程数 |
| `--device` | 自动 | 强制指定 `mps` 或 `cpu` |

## 项目结构

```
├── cli.py              # 命令行入口
├── run.command         # macOS 双击启动
├── setup_mac.sh        # 一键安装
└── mac_wm/
    ├── lama_engine.py  # LaMa 引擎（MPS/CPU 自适配、ROI 修复）
    ├── mask_utils.py   # mask 生成/清理/颜色自动检测
    ├── image_remover.py# 图片去水印
    ├── video_remover.py# 视频去水印（ffmpeg 工作流）
    └── app.py          # Gradio Web UI
```

## 常见问题

- **Q: 半透明水印涂不干净？** 调大 `--dilate`，或在 Web 界面多涂几笔
- **Q: 处理视频很慢？** 属正常（CPU 上约 1-2 秒/帧）；只涂水印小区域 + 开启 ROI 加速可显著提速
- **Q: MPS 报错？** 加 `--device cpu` 或在界面/CPU 环境运行，引擎会自动回退

## 许可

本项目代码整合自 Apache-2.0 / MIT 开源项目，遵循原项目许可，仅供学习与个人使用，请尊重内容版权。
