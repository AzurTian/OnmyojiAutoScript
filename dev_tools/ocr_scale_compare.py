"""OCR 小图放大策略对比工具 — 自动扫描模式

自动读取 log/ocr/images/ 下所有图片，对每张图应用多种放大/补边策略，
统计所有图片的综合表现，找出最佳策略。

使用方法:
    .\toolkit\python.exe dev_tools\ocr_scale_compare.py
"""
import sys
import os
import time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import cv2

from module.ocr.ppocr import TextSystem


# ============================================================
# 放大/补边策略
# ============================================================

def original(image):
    """① 原图，不做任何处理"""
    return image

def square_32(image):
    """② 当前策略: 补成正方形，边到 32 倍数（只补右下）"""
    h, w = image.shape[:2]
    length = int(max(w, h) // 32 * 32 + 32)
    border = (0, length - h, 0, length - w)
    if sum(border) > 0:
        image = cv2.copyMakeBorder(image, *border, borderType=cv2.BORDER_CONSTANT, value=(0, 0, 0))
    return image

def pad_32x_plus_32(image):
    """③ 各边补到 32 倍数，再四周加 32px"""
    h, w = image.shape[:2]
    new_w = int((w + 31) // 32 * 32)
    new_h = int((h + 31) // 32 * 32)
    image = cv2.copyMakeBorder(
        image,
        32, 32 + (new_h - h), 32, 32 + (new_w - w),
        borderType=cv2.BORDER_CONSTANT, value=(0, 0, 0)
    )
    return image

def scale_2x_nearest(image):
    """④ 2x 最近邻放大"""
    h, w = image.shape[:2]
    return cv2.resize(image, (w * 2, h * 2), interpolation=cv2.INTER_NEAREST)

def scale_2x_linear(image):
    """⑤ 2x 双线性放大"""
    h, w = image.shape[:2]
    return cv2.resize(image, (w * 2, h * 2), interpolation=cv2.INTER_LINEAR)

def scale_2x_cubic(image):
    """⑥ 2x 双三次放大"""
    h, w = image.shape[:2]
    return cv2.resize(image, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

def scale_4x_linear(image):
    """⑦ 4x 双线性放大"""
    h, w = image.shape[:2]
    return cv2.resize(image, (w * 4, h * 4), interpolation=cv2.INTER_LINEAR)

def scale_2x_pad_32(image):
    """⑧ 2x 放大 + 补边到32倍数"""
    h, w = image.shape[:2]
    scaled = cv2.resize(image, (w * 2, h * 2), interpolation=cv2.INTER_LINEAR)
    sh, sw = scaled.shape[:2]
    new_w = int((sw + 31) // 32 * 32)
    new_h = int((sh + 31) // 32 * 32)
    return cv2.copyMakeBorder(
        scaled, 0, new_h - sh, 0, new_w - sw,
        borderType=cv2.BORDER_CONSTANT, value=(0, 0, 0)
    )

def pad_32_only(image):
    """⑨ 仅四周加 32px 黑边，不缩不放"""
    h, w = image.shape[:2]
    return cv2.copyMakeBorder(image, 32, 32, 32, 32,
                              borderType=cv2.BORDER_CONSTANT, value=(0, 0, 0))

def pad_32_nosquare(image):
    """⑩ 各边补到 32 倍数（不补成正方形）"""
    h, w = image.shape[:2]
    new_w = int((w + 31) // 32 * 32)
    new_h = int((h + 31) // 32 * 32)
    return cv2.copyMakeBorder(
        image, 0, new_h - h, 0, new_w - w,
        borderType=cv2.BORDER_CONSTANT, value=(0, 0, 0)
    )


METHODS = [
    ("原图", original),
    ("正方形补32倍", square_32),
    ("各边补32+32px", pad_32x_plus_32),
    ("2x最近邻", scale_2x_nearest),
    ("2x双线性", scale_2x_linear),
    ("2x双三次", scale_2x_cubic),
    ("4x双线性", scale_4x_linear),
    ("2x放大+补边", scale_2x_pad_32),
    ("仅四周32px", pad_32_only),
    ("各边补32倍", pad_32_nosquare),
]


def collect_images() -> list[Path]:
    """自动扫描 log/ocr/images/ 下的所有 PNG 图片"""
    images_dir = Path("log/ocr/images")
    if not images_dir.exists():
        print(f"目录不存在: {images_dir.absolute()}")
        return []
    images = sorted(images_dir.rglob("*.png"))
    if not images:
        print(f"目录下没有找到 PNG 图片: {images_dir.absolute()}")
    return images


def main():
    images = collect_images()
    if not images:
        print("\n请先运行程序产生 OCR 日志图片，再运行此脚本。")
        sys.exit(1)

    print(f"找到 {len(images)} 张 OCR 图片\n")

    print("正在加载 OCR 模型...")
    ts = TextSystem()
    print("加载完成\n")

    stats = defaultdict(lambda: {"total_score": 0.0, "count": 0, "scores": [], "total_time": 0.0})

    for img_idx, img_path in enumerate(images, 1):
        image_bgr = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
        if image_bgr is None:
            continue
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        oh, ow = image_rgb.shape[:2]

        print(f"[{img_idx}/{len(images)}] {img_path.name}  ({ow}x{oh})")

        for name, func in METHODS:
            start = time.time()
            processed = func(image_rgb)
            text, score = ts.ocr_single_line(processed)
            elapsed = time.time() - start

            stats[name]["total_score"] += score
            stats[name]["count"] += 1
            stats[name]["scores"].append(score)
            stats[name]["total_time"] += elapsed

    # ============================================================
    # 汇总排名
    # ============================================================
    print("\n" + "=" * 90)
    print(f"综合排名（共 {len(images)} 张图片）")
    print("=" * 90)

    ranked = sorted(stats.items(), key=lambda x: x[1]["total_score"] / x[1]["count"], reverse=True)

    print(f"{'排名':>4s} | {'策略':14s} | {'平均分':>8s} | {'最高分':>8s} | {'最低分':>8s} | {'平均耗时':>8s}")
    print("-" * 65)
    for i, (name, s) in enumerate(ranked, 1):
        avg = s["total_score"] / s["count"]
        best = max(s["scores"])
        worst = min(s["scores"])
        avg_time = s["total_time"] / s["count"]
        print(f"{i:>4d} | {name:14s} | {avg:.4f} | {best:.4f} | {worst:.4f} | {avg_time:.3f}s")

    best_name = ranked[0][0]
    print(f"\n🏆 最佳策略: {best_name}")

    # 对每张图保存最佳策略的处理结果
    output_dir = Path("log/ocr/scale_compare")
    output_dir.mkdir(parents=True, exist_ok=True)
    best_func = dict(METHODS)[best_name]
    for img_path in images:
        image_bgr = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
        if image_bgr is None:
            continue
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        processed = best_func(image_rgb)
        out_path = output_dir / f"{img_path.stem}_{best_name}.png"
        cv2.imwrite(str(out_path), cv2.cvtColor(processed, cv2.COLOR_RGB2BGR))
    print(f"最佳策略处理结果已保存到: {output_dir}/")


if __name__ == "__main__":
    main()
