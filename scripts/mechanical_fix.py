#!/usr/bin/env python3
"""
机械首遍修复脚本 v5：
- 破折号：每章全局预算 5 个（段尾悬念优先，其次关键对话中断）
- 断句体合并：201-286 积极；287-300 保守（保留高潮排版）
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODY = ROOT / "《影笔代理人》" / "正文"

DIALOGUE_RE = re.compile(r'"[^"]*"')
CN_PUNCT = '。，！？；：、'
DASH_BUDGET = 5


def protect_dialogue(p):
    ph = []
    def _m(m):
        ph.append(m.group(0))
        return f'\x00D{len(ph)-1}\x00'
    return DIALOGUE_RE.sub(_m, p), ph


def restore_dialogue(p, ph):
    return re.sub(r'\x00D(\d+)\x00', lambda m: ph[int(m.group(1))], p)


def reduce_dashes_pass(p, keep_count, quota):
    if '——' not in p:
        return p, keep_count
    protected, ph = protect_dialogue(p)
    if '——' not in protected:
        return restore_dialogue(protected, ph), keep_count

    out = []
    cursor = 0
    for m in re.finditer(r'——', protected):
        tail = protected[m.end():].strip()
        keep = (tail == '' or tail in CN_PUNCT) and keep_count < quota
        out.append(protected[cursor:m.start()])
        if keep:
            out.append('——')
            keep_count += 1
        cursor = m.end()
    out.append(protected[cursor:])
    return restore_dialogue(''.join(out), ph), keep_count


def global_dash_budget(text, budget=DASH_BUDGET):
    total = text.count('——')
    if total <= budget:
        return text

    positions = [m.start() for m in re.finditer(r'——', text)]
    keep = [False] * len(positions)

    for i, pos in enumerate(positions):
        end = pos + 2
        tail = text[end:].split('\n\n')[0].strip()
        if tail == '' or tail in CN_PUNCT:
            keep[i] = True

    kept = sum(keep)
    remaining = max(0, budget - kept)
    for i in range(len(positions)):
        if remaining <= 0:
            break
        if not keep[i]:
            keep[i] = True
            remaining -= 1

    out = []
    cursor = 0
    for i, pos in enumerate(positions):
        out.append(text[cursor:pos])
        if keep[i]:
            out.append('——')
        else:
            prev = text[pos-1] if pos > 0 else ''
            if prev in '，。！？；：、 ':
                out.append('')
            else:
                out.append('，')
        cursor = pos + 2
    out.append(text[cursor:])
    return ''.join(out)


def merge_paragraph(p, aggressive):
    protected, ph = protect_dialogue(p)
    stripped = protected.strip()

    if len(stripped) <= 6 or stripped == '---':
        return restore_dialogue(protected, ph)

    if aggressive:
        short2 = re.compile(r'([\u4e00-\u9fff、]{1,5})。([\u4e00-\u9fff、]{1,5})。')
        for _ in range(12):
            new_p = short2.sub(r'\1，\2。', protected)
            if new_p == protected:
                break
            protected = new_p
    else:
        run3 = re.compile(r'([\u4e00-\u9fff、]{1,4})。([\u4e00-\u9fff、]{1,4})。([\u4e00-\u9fff、]{1,4})。')
        for _ in range(8):
            new_p = run3.sub(r'\1，\2，\3。', protected)
            if new_p == protected:
                break
            protected = new_p

    if aggressive:
        frag = re.compile(
            r'(?<=[，。！？；：、\x00])([\u4e00-\u9fff]{1,2})，([\u4e00-\u9fff]{1,4})(?=[，。！？；：、\x00])')
        for _ in range(20):
            new_p = frag.sub(r'\1\2', protected)
            if new_p == protected:
                break
            protected = new_p
        # 合并 "P，XY" 其中 XY 是 2-3 字（不管后面是什么）
        frag_b = re.compile(
            r'(?<=[，。！？；：、\x00])([\u4e00-\u9fff]{1,2})，([\u4e00-\u9fff]{2,3})(?=[\u4e00-\u9fff])')
        for _ in range(15):
            new_p = frag_b.sub(r'\1\2', protected)
            if new_p == protected:
                break
            protected = new_p
        # 合并短句号："X。Y" 其中 X,Y 都是 1-4 字，X 前面是标点/行首
        frag_c = re.compile(
            r'(?<=[，。！？；：、\x00\n])([\u4e00-\u9fff]{1,3})。([\u4e00-\u9fff]{1,3})(?=[，。！？；：、\x00\n])')
        for _ in range(15):
            new_p = frag_c.sub(r'\1\2', protected)
            if new_p == protected:
                break
            protected = new_p
        frag2 = re.compile(
            r'(?<=[，。！？；：、\x00])([\u4e00-\u9fff]{1,2})，([\u4e00-\u9fff]{2,5})。')
        for _ in range(10):
            new_p = frag2.sub(r'\1\2。', protected)
            if new_p == protected:
                break
            protected = new_p
        frag3 = re.compile(
            r'(^|\n)([\u4e00-\u9fff]{1,2})，([\u4e00-\u9fff]{1,3})，')
        for _ in range(10):
            new_p = frag3.sub(r'\1\2\3，', protected)
            if new_p == protected:
                break
            protected = new_p
    else:
        frag3 = re.compile(
            r'(?<=[，。！？；：、\x00])([\u4e00-\u9fff]{1,2})，([\u4e00-\u9fff]{1,2})，([\u4e00-\u9fff]{1,4})(?=[，。！？；：、\x00])')
        for _ in range(12):
            new_p = frag3.sub(r'\1\2\3', protected)
            if new_p == protected:
                break
            protected = new_p

    return restore_dialogue(protected, ph)


def process_chapter(fpath, ch):
    text = fpath.read_text(encoding='utf-8')
    parts = re.split(r'(\n\s*\n)', text)

    is_climax = ch >= 287
    aggressive = not is_climax
    quota = 3
    keep_count = 0

    new_parts = []
    for part in parts:
        if part.strip() == '' or part.strip() == '---' or '【End of file' in part:
            new_parts.append(part)
            continue
        p, keep_count = reduce_dashes_pass(part, keep_count, quota)
        p = merge_paragraph(p, aggressive)
        new_parts.append(p)

    new_text = ''.join(new_parts)
    new_text = global_dash_budget(new_text, DASH_BUDGET)
    fpath.write_text(new_text, encoding='utf-8')
    return text, new_text


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 201
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    for ch in range(start, end + 1):
        matches = list(BODY.glob(f'第{ch:03d}章*.md'))
        if not matches:
            continue
        fpath = matches[0]
        old, new = process_chapter(fpath, ch)
        print(f'第{ch:03d}章: 破折号 {old.count("——")} -> {new.count("——")}')


if __name__ == '__main__':
    main()
