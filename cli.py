#!/usr/bin/env python3
"""Mac 图片与视频水印去除 - 命令行入口。

示例：
  python cli.py image  -i 照片.jpg -m mask.png -o 结果.png
  python cli.py image  -i 照片.jpg -b 100,80,420,160 -o 结果.png
  python cli.py batch  -d 图片目录 -m mask目录 -o 输出目录
  python cli.py video  -i 视频.mp4 -b 1180,60,1860,130 -o 结果.mp4
  python cli.py video  -i 视频.mp4 -m mask.png -o 结果.mp4
  python cli.py server                  # 启动 Web UI
"""

import argparse
import sys

from PIL import Image

from mac_wm.image_remover import remove_watermark, batch_remove
from mac_wm.video_remover import remove_video_watermark
from mac_wm.mask_utils import mask_from_boxes
from mac_wm.lama_engine import pick_device


def parse_boxes(s: str):
    """'x1,y1,x2,y2; x1,y1,x2,y2' -> [(x1,y1,x2,y2), ...]"""
    boxes = []
    for part in s.split(";"):
        nums = [float(v) for v in part.replace("，", ",").split(",")]
        if len(nums) != 4:
            raise ValueError(f"坐标需要 4 个数字: {part}")
        boxes.append(tuple(nums))
    return boxes


def main():
    p = argparse.ArgumentParser(description="Mac 图片与视频水印去除工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("image", help="图片去水印")
    pi.add_argument("-i", "--input", required=True)
    pi.add_argument("-o", "--output", required=True)
    pi.add_argument("-m", "--mask", help="mask 图片（白色=水印）")
    pi.add_argument("-b", "--boxes",
                    help="水印矩形 x1,y1,x2,y2（分号分隔多个）")
    pi.add_argument("--dilate", type=int, default=4, help="mask 外扩像素")
    pi.add_argument("--no-roi", action="store_true", help="关闭 ROI 加速")
    pi.add_argument("--device", choices=["mps", "cpu"], default=None)

    pb = sub.add_parser("batch", help="批量图片去水印")
    pb.add_argument("-d", "--input-dir", required=True)
    pb.add_argument("-m", "--mask-dir", required=True)
    pb.add_argument("-o", "--output-dir", required=True)
    pb.add_argument("--dilate", type=int, default=4)
    pb.add_argument("--no-roi", action="store_true")

    pv = sub.add_parser("video", help="视频去水印")
    pv.add_argument("-i", "--input", required=True)
    pv.add_argument("-o", "--output", required=True)
    pv.add_argument("-m", "--mask", help="mask 图片（白色=水印）")
    pv.add_argument("-b", "--boxes", help="水印矩形 x1,y1,x2,y2")
    pv.add_argument("--dilate", type=int, default=6)
    pv.add_argument("--workers", type=int, default=2)
    pv.add_argument("--no-roi", action="store_true")
    pv.add_argument("--no-audio", action="store_true", help="不保留音频")

    ps = sub.add_parser("server", help="启动 Web UI")

    args = p.parse_args()
    print(f"推理设备: {pick_device()}")

    if args.cmd == "image":
        image = Image.open(args.input).convert("RGB")
        mask = _load_or_build_mask(args.mask, args.boxes, image.size)
        result = remove_watermark(image, mask, dilate_px=args.dilate,
                                  roi_mode=not args.no_roi,
                                  device=args.device)
        result.save(args.output, quality=95)
        print(f"✅ 已输出: {args.output}")

    elif args.cmd == "batch":
        done = batch_remove(args.input_dir, args.mask_dir, args.output_dir,
                            dilate_px=args.dilate,
                            roi_mode=not args.no_roi)
        print(f"✅ 完成 {len(done)} 张 -> {args.output_dir}")

    elif args.cmd == "video":
        mask = _load_or_build_mask(args.mask, args.boxes, None)
        out = remove_video_watermark(
            args.input, mask, args.output, dilate_px=args.dilate,
            workers=args.workers, roi_mode=not args.no_roi,
            keep_audio=not args.no_audio)
        print(f"✅ 已输出: {out}")

    elif args.cmd == "server":
        from mac_wm.app import main
        main()


def _load_or_build_mask(mask_path, boxes, size):
    if mask_path:
        return Image.open(mask_path).convert("L")
    if boxes:
        if size is None:
            raise SystemExit("视频模式请先给 --mask 或 --boxes（尺寸取自视频首帧）")
        return mask_from_boxes(parse_boxes(boxes), size)
    raise SystemExit("需要 -m mask 文件或 -b 坐标框")


if __name__ == "__main__":
    sys.exit(main())
