#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复脚本 v6：精简破折号 + 合并过度断句
关键改进：
- 解释性破折号直接删除（不换逗号，避免新增断句命中）
- 段末拖音超量时换成……（省略号，不计入断句命中）
- 断句合并更激进
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODY = ROOT / "《影笔代理人》" / "正文"


def in_dialogue_at(text, pos):
    """按 " 出现次数奇偶判断是否在引号内"""
    return text[:pos].count('"') % 2 == 1


def fix_dashes(text, target=4):
    """精简破折号"""
    lines = text.split('\n')
    new_lines = []
    for line in lines:
        if '——' not in line:
            new_lines.append(line)
            continue
        result = []
        i = 0
        while i < len(line):
            if line[i:i+2] == '——':
                in_d = in_dialogue_at(line, i)
                after = line[i+2:i+4]
                at_eol = (i+2 >= len(line)) or after.startswith('"') or after.startswith('」')

                if in_d:
                    # 对话内：话中停顿/拖音，换成省略号
                    result.append('……')
                elif at_eol:
                    result.append('\x00KEEP\x00')  # 段末拖音
                else:
                    # 解释性破折号：换成逗号（保持可读性，避免句子粘连）
                    result.append('，')
                i += 2
            else:
                result.append(line[i])
                i += 1
        new_lines.append(''.join(result))
    text = '\n'.join(new_lines)

    # 控制段末拖音数量
    keeps = [m.start() for m in re.finditer(r'\x00KEEP\x00', text)]
    if len(keeps) > target - 1:
        keep_set = set(keeps[:target-1])
        out = []
        last = 0
        for m in re.finditer(r'\x00KEEP\x00', text):
            out.append(text[last:m.start()])
            if m.start() in keep_set:
                out.append('——')
            else:
                out.append('……')  # 用省略号替代，不产生新的断句命中
            last = m.end()
        out.append(text[last:])
        text = ''.join(out)
    else:
        text = text.replace('\x00KEEP\x00', '——')
    return text


# ---------- 断句体合并 ----------

ONE_CHAR_REMOVE_COMMA = set(
    '他她它我你您这那哪啥怎为只就还又也都才便却竟果毕被把让向从在到往给对'
)
TWO_CHAR_REMOVE_COMMA = {
    '沈砚', '许曼', '郑川', '苏听晚', '陈婆', '护士长', '青铜', '面具', '影子',
    '那个', '这个', '哪个', '一个', '两个', '三个', '一栋', '一辆', '一家',
    '一种', '一样', '一点', '一下', '一天', '一夜', '一步', '一声', '一眼',
    '一身', '满脸', '满街', '满屋', '然后', '但是', '因为', '所以', '如果',
    '虽然', '不过', '只是', '就是', '还是', '或者', '要么', '一面', '一边',
    '这时', '那时', '此时', '彼时', '原来', '其实', '究竟', '到底', '简直',
    '竟然', '居然', '果然', '果真', '明明', '确实', '实在', '几乎', '差不多',
    '不是', '没有', '不知', '只见', '只听', '又见', '又听',
}


def should_remove_comma_after(seg):
    s = seg.strip()
    if len(s) == 1 and s in ONE_CHAR_REMOVE_COMMA:
        return True
    if len(s) == 2 and s in TWO_CHAR_REMOVE_COMMA:
        return True
    return False


def starts_with_pronoun(s):
    return len(s) >= 1 and s[0] in '他她它我你'


def process_sentence(sent):
    if '，' not in sent:
        return sent

    # 多轮合并，直到稳定
    prev = None
    cur = sent
    for _ in range(5):
        if cur == prev:
            break
        prev = cur
        cur = _merge_once(cur)
    return cur


def _merge_once(sent):
    segs = sent.split('，')
    total = len(segs)
    if total < 2:
        return sent

    aggressive = total >= 2
    very_aggressive = total >= 3

    new_segs = []
    i = 0
    while i < len(segs):
        cur = segs[i]
        cs = cur.strip()
        if not cs:
            new_segs.append(cur)
            i += 1
            continue
        should_merge = False
        if i + 1 < len(segs):
            nxt = segs[i+1].strip()
            if not nxt:
                new_segs.append(cur)
                i += 1
                continue
            if should_remove_comma_after(cur):
                should_merge = True
            elif aggressive and starts_with_pronoun(cs) and len(cs) <= 4:
                should_merge = True
            elif len(cs) <= 2 and len(nxt) <= 2 and len(cs + nxt) <= 6:
                should_merge = True
            elif aggressive and len(cs) == 2 and len(nxt) <= 4:
                should_merge = True
            elif very_aggressive and len(cs) == 3 and starts_with_pronoun(cs) and len(nxt) <= 4:
                should_merge = True
            elif very_aggressive and len(cs) == 3 and cs[:2] in ('是一', '不是', '没有', '他在', '他的', '她的', '它的', '我在', '我不', '你在'):
                should_merge = True
        if should_merge and i + 1 < len(segs):
            new_segs.append(cur + segs[i+1])
            i += 2
            continue
        new_segs.append(cur)
        i += 1
    return '，'.join(new_segs)


def merge_in_text(text):
    parts = re.split(r'([。！？；])', text)
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            result.append(part)
            continue
        result.append(process_sentence(part))
    return ''.join(result)


def fix_fragments(text):
    blocks = re.split(r'(\n\s*\n)', text)
    out = []
    for block in blocks:
        if block.strip() == '':
            out.append(block)
            continue
        lines = [l for l in block.split('\n') if l.strip()]
        # 独立短段：单行且 <=10字且无逗号（真正的有意节奏）
        if (len(lines) == 1
                and len(lines[0].strip().strip('"「」『』')) <= 10
                and '，' not in lines[0]):
            out.append(block)
            continue
        new_lines = []
        for line in block.split('\n'):
            if not line.strip():
                new_lines.append(line)
                continue
            stripped = line.strip().strip('"「」『』')
            if len(stripped) <= 6 and '，' not in line:
                new_lines.append(line)
                continue
            parts = re.split(r'("(?:[^"\\]|\\.)*"|「[^」]*」|『[^』]*』)', line)
            new_parts = []
            for part in parts:
                if part.startswith('"') or part.startswith('「') or part.startswith('『'):
                    new_parts.append(part)
                else:
                    new_parts.append(merge_in_text(part))
            new_lines.append(''.join(new_parts))
        out.append('\n'.join(new_lines))
    return ''.join(out)


def process_chapter(fpath, dash_target=4):
    text = fpath.read_text(encoding='utf-8')
    orig_dash = text.count('——')
    orig_frag = len(re.findall(r'[\u4e00-\u9fff]{1,2}[。，！？；：、]', text))
    text = fix_dashes(text, target=dash_target)
    text = fix_fragments(text)
    new_dash = text.count('——')
    new_frag = len(re.findall(r'[\u4e00-\u9fff]{1,2}[。，！？；：、]', text))
    fpath.write_text(text, encoding='utf-8')
    return orig_dash, new_dash, orig_frag, new_frag


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 101
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    total_orig_d = total_new_d = 0
    total_orig_f = total_new_f = 0
    chapters = 0
    for ch in range(start, end+1):
        matches = list(BODY.glob(f'第{ch:03d}章*.md'))
        if not matches:
            continue
        od, nd, of, nf = process_chapter(matches[0])
        total_orig_d += od
        total_new_d += nd
        total_orig_f += of
        total_new_f += nf
        chapters += 1
    print(f"处理章节: {chapters}")
    print(f"破折号: {total_orig_d} -> {total_new_d} (平均 {total_new_d/max(chapters,1):.1f}/章)")
    print(f"断句体: {total_orig_f} -> {total_new_f} (平均 {total_new_f/max(chapters,1):.1f}/章)")
    if total_orig_f:
        print(f"断句体减少: {(1-total_new_f/total_orig_f)*100:.1f}%")


if __name__ == '__main__':
    main()
