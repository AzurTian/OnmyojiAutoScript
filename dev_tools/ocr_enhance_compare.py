"""OCR 图像增强对比工具 — 自动扫描模式

自动读取 log/ocr/images/ 下所有图片，对每张图应用多种增强方式，
统计所有图片的综合表现，找出最佳增强策略。

使用方法:
    .\toolkit\python.exe dev_tools\ocr_enhance_compare.py
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
# 增强方法定义
# ============================================================

def enhance_original(image):
    """① 原图，不做任何处理"""
    return image

def enhance_gray(image):
    """② 灰度化"""
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)

def enhance_binary_otsu(image):
    """③ 大津二值化"""
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)

def enhance_binary_inv(image):
    """④ 反色大津二值化（白底黑字→黑底白字）"""
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)

def enhance_adaptive(image):
    """⑤ 自适应阈值"""
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, 15, 2)
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)

def enhance_contrast(image):
    """⑥ 对比度增强（直方图均衡化）"""
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    equalized = cv2.equalizeHist(gray)
    return cv2.cvtColor(equalized, cv2.COLOR_GRAY2RGB)

def enhance_clahe(image):
    """⑦ CLAHE 自适应直方图均衡化"""
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)

def enhance_sharpen(image):
    """⑧ 锐化"""
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    sharpened = cv2.filter2D(image, -1, kernel)
    return sharpened

def enhance_denoise(image):
    """⑨ 中值去噪"""
    denoised = cv2.medianBlur(image, 3)
    return denoised

def enhance_bilateral(image):
    """⑩ 双边滤波（保边去噪）"""
    filtered = cv2.bilateralFilter(image, 9, 75, 75)
    return filtered

def enhance_morph_close(image):
    """⑪ 形态学闭运算（填充细小缺口）"""
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = np.ones((2, 2), np.uint8)
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
    return cv2.cvtColor(closed, cv2.COLOR_GRAY2RGB)

def enhance_morph_open(image):
    """⑫ 形态学开运算（去除噪点）"""
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel = np.ones((2, 2), np.uint8)
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    return cv2.cvtColor(opened, cv2.COLOR_GRAY2RGB)


ENHANCE_METHODS = [
    ("原图", enhance_original),
    ("灰度化", enhance_gray),
    ("大津二值化", enhance_binary_otsu),
    ("反色二值化", enhance_binary_inv),
    ("自适应阈值", enhance_adaptive),
    ("直方图均衡化", enhance_contrast),
    ("CLAHE均衡化", enhance_clahe),
    ("锐化", enhance_sharpen),
    ("中值去噪", enhance_denoise),
    ("双边滤波", enhance_bilateral),
    ("闭运算(填缺口)", enhance_morph_close),
    ("开运算(去噪点)", enhance_morph_open),
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

        for name, func in ENHANCE_METHODS:
            start = time.time()
            enhanced = func(image_rgb)
            text, score = ts.ocr_single_line(enhanced)
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

    print(f"{'排名':>4s} | {'增强方式':12s} | {'平均分':>8s} | {'最高分':>8s} | {'最低分':>8s} | {'平均耗时':>8s}")
    print("-" * 65)
    for i, (name, s) in enumerate(ranked, 1):
        avg = s["total_score"] / s["count"]
        best = max(s["scores"])
        worst = min(s["scores"])
        avg_time = s["total_time"] / s["count"]
        print(f"{i:>4d} | {name:12s} | {avg:.4f} | {best:.4f} | {worst:.4f} | {avg_time:.3f}s")

    best_name = ranked[0][0]
    print(f"\n🏆 最佳增强方式: {best_name}")

    # 保存最佳策略处理结果
    output_dir = Path("log/ocr/enhance_compare")
    output_dir.mkdir(parents=True, exist_ok=True)
    best_func = dict(ENHANCE_METHODS)[best_name]
    for img_path in images:
        image_bgr = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
        if image_bgr is None:
            continue
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        processed = best_func(image_rgb)
        out_path = output_dir / f"{img_path.stem}_{best_name}.png"
        cv2.imwrite(str(out_path), cv2.cvtColor(processed, cv2.COLOR_RGB2BGR))
    print(f"最佳增强处理结果已保存到: {output_dir}/")


if __name__ == "__main__":
    main()
