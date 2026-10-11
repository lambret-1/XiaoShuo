#!/usr/bin/env python3
"""
机械修复脚本 v5：第001-100章
策略：
- 破折号：对话中断保留(3-5个/章)，其余转逗号/句号
- 断句体：在纯叙述段落中，删除大部分逗号，只保留：
  1. 段首第一个逗号（场景/话题）
  2. 转折连词前的逗号（但/可/却/而/不过/但是/可是）
  3. 时间从句后的逗号（的时候/之后/以前/以来）
  4. 数字/年龄后的逗号
- 对话和对话间动作拍完全保护
"""
import os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODY = ROOT / "《影笔代理人》" / "正文"

def split_segments(text):
    """分段：'dialogue'=引号内, 'beat'=引号间动作, 'narration'=纯叙述"""
    parts = []
    pattern = re.compile(r'"[^"]*"')
    last = 0
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        if m.start() > last:
            seg = text[last:m.start()]
            # 引号之间的段都是 beat（动作拍），保护
            if i > 0:
                parts.append((seg, 'beat'))
            else:
                parts.append((seg, 'narration'))
        parts.append((m.group(0), 'dialogue'))
        last = m.end()
    if last < len(text):
        parts.append((text[last:], 'narration'))
    return parts

def fix_dashes(text):
    lines = text.split('\n')
    dash_info = []
    for li, line in enumerate(lines):
        idx = 0
        while True:
            pos = line.find('——', idx)
            if pos == -1:
                break
            rest = line[pos+2:].strip()
            is_line_end = (rest == '' or rest.startswith('。') or rest.startswith('，') or rest.startswith('"'))
            before = line[max(0,pos-3):pos]
            after = line[pos+2:pos+4]
            after_quote = before.endswith('"') or before.endswith('"')
            before_quote = after.startswith('"') or after.startswith('"')
            dash_info.append((li, pos, is_line_end, after_quote, before_quote))
            idx = pos + 2

    if not dash_info:
        return text

    keep = set()
    for i, (li, pos, is_end, aq, bq) in enumerate(dash_info):
        if aq or bq:
            keep.add(i)
    if len(keep) < 3:
        for i, d in enumerate(dash_info):
            if i not in keep and not d[2]:
                keep.add(i)
                if len(keep) >= 3:
                    break

    replacements = {}
    for i, (li, pos, is_end, aq, bq) in enumerate(dash_info):
        if i in keep:
            continue
        if is_end:
            replacements.setdefault(li, []).append((pos, '。'))
        else:
            replacements.setdefault(li, []).append((pos, '，'))

    for li, reps in replacements.items():
        line = lines[li]
        for pos, new_str in sorted(reps, key=lambda x: -x[0]):
            line = line[:pos] + new_str + line[pos+2:]
        lines[li] = line
    return '\n'.join(lines)

def agressive_comma_removal(narration_text):
    """在纯叙述文本中删除多余逗号"""
    # 按行/段处理
    lines = narration_text.split('\n')
    new_lines = []

    for line in lines:
        if not line.strip():
            new_lines.append(line)
            continue

        # 保护规则：找到所有必须保留的逗号位置
        keep_positions = set()

        # 1. 段首第一个逗号保留（场景设定）
        first_comma = line.find('，')
        if first_comma != -1:
            keep_positions.add(first_comma)

        # 2. 转折连词前的逗号：，但/，可/，却/，而/，不过/，但是/，可是/，只是/，就是/，然而
        for m in re.finditer(r'，(但是|可是|不过|只是|就是|然而|但|可|却|而)', line):
            keep_positions.add(m.start())

        # 3. 时间从句后的逗号：的时候，/之后，/以前，/以来，/为止，/当时，/同时，/那时，
        for m in re.finditer(r'(的时候|之后|以前|以来|为止|当时|同时|那时)，', line):
            keep_positions.add(m.end() - 1)

        # 4. 数字/年龄后的逗号：三十二三岁，/二十七八岁，/三十二三年，
        for m in re.finditer(r'([\u4e00-\u9fff]*[一二三四五六七八九十百零半几][\u4e00-\u9fff]*岁)，', line):
            keep_positions.add(m.end() - 1)

        # 5. 引号前的逗号（引出对话）：，"
        for m in re.finditer(r'，"', line):
            keep_positions.add(m.start())

        # 6. 保护 "X说，" "X道，" "X问，" 等对话标签（在叙述中可能出现）
        for m in re.finditer(r'[\u4e00-\u9fff]{1,4}(说|道|问|答|开口|低声|沉声|轻声|淡淡|冷冷|笑|叹)，', line):
            keep_positions.add(m.end() - 1)

        # 7. 保护 "：" 前面的逗号（引出下文）
        # 8. 保护 "……" 前面的逗号

        # 现在删除不在 keep_positions 中的逗号
        result = []
        for i, ch in enumerate(line):
            if ch == '，' and i not in keep_positions:
                continue  # 删除这个逗号
            result.append(ch)
        new_lines.append(''.join(result))

    return '\n'.join(new_lines)

def process_chapter(fpath):
    text = fpath.read_text(encoding='utf-8')
    original = text
    text = fix_dashes(text)

    segments = split_segments(text)
    new_segments = []
    for seg, mode in segments:
        if mode == 'narration':
            new_segments.append(agressive_comma_removal(seg))
        else:
            new_segments.append(seg)
    text = ''.join(new_segments)

    if text != original:
        fpath.write_text(text, encoding='utf-8')
        return True
    return False

def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    changed = 0
    for ch in range(start, end+1):
        matches = list(BODY.glob(f"第{ch:03d}章*.md"))
        if not matches:
            continue
        if process_chapter(matches[0]):
            changed += 1
    print(f"共修复 {changed} 章")

if __name__ == '__main__':
    main()
