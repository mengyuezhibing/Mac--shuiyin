"""Mac 图片与视频水印去除工具

整合自以下开源项目思路：
- IOPaint / Lama Cleaner (github.com/Sanster/IOPaint) — LaMa 图片修复
- WatermarkRemover-AI (github.com/D-Ogi/WatermarkRemover-AI) — 检测+修复流程
- ProPainter (github.com/sczhou/ProPainter) / video-watermark-removal — 视频逐帧修复流程

针对 macOS（含 Apple Silicon MPS 加速）整合重写。
"""

__version__ = "1.0.0"
