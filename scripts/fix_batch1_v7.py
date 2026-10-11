#!/usr/bin/env python3
"""
机械修复脚本 v7：第001-100章
结合 v5 激进删除 + v6 新主语保护
- 破折号：对话中断保留(3-5个/章)，其余转逗号/句号
- 断句体：在叙述中删除大部分逗号，但保留：
  1. 段首第一个逗号
  2. 新主语前的逗号（他/她/它/这/那/人名/名词开头）
  3. 转折连词前的逗号
  4. 时间从句后的逗号
  5. 对话标签后的逗号
- 对话和对话间动作拍完全保护
"""
import os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODY = ROOT / "《影笔代理人》" / "正文"

def split_segments(text):
    parts = []
    pattern = re.compile(r'"[^"]*"')
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

def keep_comma(line, pos):
    """判断 pos 位置的逗号是否保留"""
    after = line[pos+1:pos+5]

    # 引号前逗号保留
    if after.startswith('"') or after.startswith('"'):
        return True

    # 转折连词保留
    if re.match(r'(但是|可是|不过|只是|就是|然而|但|可|却|而|因为|所以|如果|虽然|即使|只有|只要)', after):
        return True

    # 时间从句保留
    if re.match(r'(的时候|以后|以前|以来|同时|当时|那时)', after):
        return True

    # 新主语：代词/人名保留（新句子主语）
    if re.match(r'(他|她|它|我|你|这|那|谁|什么|怎么|沈砚|周明|苏听晚|陈婆婆|赵国栋|男人|女人|老人|女孩|男孩)', after):
        return True

    # 场景/地点开头保留（新话题）
    if re.match(r'(画室|窗外|门外|屋内|街上|路上|屋里|房间|地板|墙壁|灯光|阳光|月光)', after):
        return True

    # 对话标签（X说/X道/X问/X答）保留
    before = line[max(0,pos-4):pos]
    if re.search(r'(说|道|问|答|开口|低声|沉声|轻声|淡淡|冷冷|笑|叹)$', before):
        return True

    # 数字/年龄后的逗号保留
    if re.search(r'[一二三四五六七八九十百零半几][岁年月日天]$', before):
        return True

    # 默认：删除逗号（更激进）
    return False

def process_narration(narration_text):
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
        # 第一个逗号总是保留（段首场景）
        keep.add(comma_positions[0])
        for pos in comma_positions[1:]:
            if keep_comma(line, pos):
                keep.add(pos)

        result = []
        for i, ch in enumerate(line):
            if ch == '，' and i not in keep:
                continue
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
            new_segments.append(process_narration(seg))
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
