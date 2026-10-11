#!/usr/bin/env python3
"""
机械修复脚本 v6：第001-100章
策略：
- 破折号：对话中断保留(3-5个/章)，其余转逗号/句号
- 断句体：智能删除叙述中多余逗号
  * 删除：同一主语下连续动词短语间的逗号（逗号后是动词）
  * 保留：新主语前的逗号（逗号后是代词/人名）
  * 保留：转折连词、时间从句、对话标签、段首场景
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

# 逗号后如果是这些词，保留逗号（新主语/新话题）
KEEP_AFTER_COMMA = [
    '他', '她', '它', '我', '你', '这', '那', '谁', '什么', '怎么',
    '沈砚', '周明', '苏听晚', '陈婆婆', '赵国栋', '男人', '女人', '老人',
    '画室', '窗外', '门外', '屋内', '街上', '路上', '屋里', '房间',
    '但', '但是', '可', '可是', '却', '而', '然而', '不过', '只是',
    '因为', '所以', '如果', '虽然', '即使', '只有', '只要',
    '的时候', '之后', '以前', '以来', '同时', '当时',
    '然后', '接着', '最后', '于是', '终于', '这时', '那时',
    '声音', '目光', '表情', '脸色', '眼神', '嘴角', '眉头',
    '墨痕', '影子', '脚步', '呼吸', '身体', '手指',
]

# 逗号后如果是动词/副词/形容词，删除逗号（同一主语连续动作）
VERB_AFTER_COMMA = [
    '看', '听', '说', '想', '走', '站', '坐', '转', '抬', '低',
    '伸', '收', '画', '写', '拿', '放', '按', '推', '拉', '开',
    '关', '点', '摇', '叹', '吸', '笑', '哭', '愣', '醒', '睡',
    '等', '追', '跑', '跳', '蹲', '跪', '靠', '倚', '扶', '握',
    '松', '皱', '闭', '睁', '眨', '回', '过', '起', '下', '进',
    '出', '上', '下', '来', '去', '起', '停', '顿', '接', '跟',
    '像', '是', '在', '有', '没', '不', '很', '太', '更', '最',
    '又', '也', '还', '就', '才', '都', '只', '便', '仍', '已',
    '把', '被', '让', '使', '给', '向', '往', '从', '到', '于',
]

def should_remove_comma(line, comma_pos):
    """判断逗号是否应该删除"""
    after = line[comma_pos+1:comma_pos+6]

    # 保护：引号前逗号
    if after.startswith('"') or after.startswith('"'):
        return False

    # 保护：新主语/新话题
    for w in KEEP_AFTER_COMMA:
        if after.startswith(w):
            return False

    # 保护：段首第一个逗号（场景设定）
    # （由调用者处理）

    # 删除：动词/副词/形容词开头（连续动作）
    for w in VERB_AFTER_COMMA:
        if after.startswith(w):
            return True

    # 默认：保留逗号（安全）
    return False

def process_narration(narration_text):
    lines = narration_text.split('\n')
    new_lines = []
    for line in lines:
        if not line.strip():
            new_lines.append(line)
            continue

        # 找到所有逗号位置
        comma_positions = [i for i, ch in enumerate(line) if ch == '，']
        if not comma_positions:
            new_lines.append(line)
            continue

        # 第一个逗号保留（段首场景）
        keep = {comma_positions[0]}

        # 其余逗号：判断是否删除
        for pos in comma_positions[1:]:
            if not should_remove_comma(line, pos):
                keep.add(pos)

        # 构建新行
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
