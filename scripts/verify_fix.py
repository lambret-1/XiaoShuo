#!/usr/bin/env python3
"""
修复进度验证脚本：统计指定章节范围内的破折号数和断句体命中数。
用法: python3 verify_fix.py <起始章号> <结束章号>
"""
import os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODY = ROOT / "《影笔代理人》" / "正文"

def count_dashes(text):
    """统计破折号——的数量"""
    return text.count("——")

def count_punct_abuse(text):
    """统计单字/双字后紧接标点的次数（与bug检测逻辑一致）
    匹配：1-2个中文字符后紧跟 。，！？；：、
    """
    # 匹配中文字符（含常用标点外的汉字）
    pattern = r'[\u4e00-\u9fff]{1,2}[。，！？；：、]'
    return len(re.findall(pattern, text))

def main():
    if len(sys.argv) < 3:
        print("用法: python3 verify_fix.py <起始章号> <结束章号>")
        sys.exit(1)
    start = int(sys.argv[1])
    end = int(sys.argv[2])

    total_dash = 0
    total_punct = 0
    chapters = 0
    high_dash = []
    high_punct = []

    for ch in range(start, end + 1):
        # 找到对应文件
        pattern = f"第{ch:03d}章*.md"
        matches = list(BODY.glob(pattern))
        if not matches:
            # 尝试非零填充
            pattern2 = f"第{ch}章*.md"
            matches = list(BODY.glob(pattern2))
        if not matches:
            continue
        fpath = matches[0]
        text = fpath.read_text(encoding="utf-8")
        d = count_dashes(text)
        p = count_punct_abuse(text)
        total_dash += d
        total_punct += p
        chapters += 1
        if d > 7:
            high_dash.append((ch, d))
        if p > 400:
            high_punct.append((ch, p))

    print(f"章节范围: 第{start:03d}-{end:03d}章")
    print(f"实际扫描: {chapters} 章")
    print(f"破折号总数: {total_dash} (平均 {total_dash/max(chapters,1):.1f}/章)")
    print(f"断句体命中数: {total_punct} (平均 {total_punct/max(chapters,1):.1f}/章)")
    if high_dash:
        print(f"\n破折号>7的章节 ({len(high_dash)}章):")
        for ch, d in high_dash[:20]:
            print(f"  第{ch:03d}章: {d}个")
    if high_punct:
        print(f"\n断句体>400的章节 ({len(high_punct)}章):")
        for ch, p in high_punct[:20]:
            print(f"  第{ch:03d}章: {p}处")

if __name__ == "__main__":
    main()
