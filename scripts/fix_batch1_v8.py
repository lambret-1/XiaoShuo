#!/usr/bin/env python3
"""
机械修复脚本 v8（最终版）：第001-100章
- 破折号：对话中断保留(3-5个/章)，其余转逗号/句号
- 断句体：
  * 删除叙述中大部分逗号（只保留转折连词、时间从句、对话标签、引号前逗号）
  * 合并极短独立段（<=6字非对话）到上一段
- 对话和动作拍完全保护
"""
import os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODY = ROOT / "《影笔代理人》" / "正文"

def split_segments(text):
    parts = []
    # 匹配中文弯引号 "..." (U+201C, U+201D)
    pattern = re.compile(r'[\u201c][^\u201d]*[\u201d]')
    last = 0
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        if m.start() > last:
            seg = text[last:m.start()]
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
            is_line_end = (rest == '' or rest.startswith('。') or rest.startswith('，') or rest.startswith('\u201c'))
            before = line[max(0,pos-3):pos]
            after = line[pos+2:pos+4]
            after_quote = before.endswith('\u201d')
            before_quote = after.startswith('\u201c')
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

def process_narration(narration_text):
    """在纯叙述中删除大部分逗号"""
    lines = narration_text.split('\n')
    new_lines = []
    for line in lines:
        if not line.strip():
            new_lines.append(line)
            continue

        comma_positions = [i for i, ch in enumerate(line) if ch == '，']
        if not comma_positions:
            new_lines.append(line)
            continue

        keep = set()
        for pos in comma_positions:
            after = line[pos+1:pos+5]
            before = line[max(0,pos-5):pos]

            # 保留：引号前逗号
            if after.startswith('\u201c') or after.startswith('\u201d'):
                keep.add(pos); continue
            # 保留：转折连词
            if re.match(r'(但是|可是|不过|只是|就是|然而|但|可|却|而|因为|所以|如果|虽然|即使)', after):
                keep.add(pos); continue
            # 保留：时间从句
            if re.match(r'(的时候|以后|以前|以来|同时|当时)', after):
                keep.add(pos); continue
            # 保留：对话标签
            if re.search(r'(说|道|问|答|开口|低声|沉声|轻声|淡淡|冷冷|笑|叹)$', before):
                keep.add(pos); continue
            # 保留：年龄/数字
            if re.search(r'[一二三四五六七八九十百零半几][岁年月日天]$', before):
                keep.add(pos); continue

        # 构建新行
        result = []
        for i, ch in enumerate(line):
            if ch == '，' and i not in keep:
                continue
            result.append(ch)
        new_lines.append(''.join(result))

    return '\n'.join(new_lines)

def merge_short_paragraphs(text):
    """合并极短独立段（<=6字，非对话、非标题）到上一段"""
    paragraphs = text.split('\n\n')
    merged = []
    for p in paragraphs:
        stripped = p.strip()
        # 判断是否是极短段
        is_short = (len(stripped) <= 4
                    and stripped
                    and not stripped.startswith('#')
                    and not stripped.startswith('\u201c')
                    and not stripped.startswith('\u201d')
                    and not stripped.startswith('---'))
        if is_short and merged:
            # 合并到上一段：去掉上一段末尾的句号，加逗号，加短段，加句号
            prev = merged[-1].rstrip()
            if prev.endswith('。'):
                prev = prev[:-1]
            merged[-1] = prev + '，' + stripped + '。'
        else:
            merged.append(p)
    return '\n\n'.join(merged)

def process_chapter(fpath):
    text = fpath.read_text(encoding='utf-8')
    original = text
    text = fix_dashes(text)

    segments = split_segments(text)
    new_segments = []
    for seg, mode in segments:
        if mode == 'narration':
            new_segments.append(process_narration(seg))
        else:
            new_segments.append(seg)
    text = ''.join(new_segments)

    # 合并短段（保守版：只合并<=4字的极短段）
    text = merge_short_paragraphs(text)

    # 清理：双句号、双逗号、行尾多余标点
    text = text.replace('。。', '。')
    text = text.replace('，，', '，')
    text = text.replace('。，', '。')
    text = text.replace('：。', '：')
    # 引号前的逗号清理
    text = re.sub(r'，(\u201d)', r'\1', text)
    text = re.sub(r'([\u4e00-\u9fff])，(\u201c)', r'\1，\2', text)  # 保持引号前逗号

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
