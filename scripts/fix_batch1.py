#!/usr/bin/env python3
"""
机械修复脚本：第001-100章破折号精简 + 断句体合并
- 破折号：每章保留3-5个，其余转为逗号
- 断句体：删除叙述中多余的逗号，合并连续短句
"""
import os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODY = ROOT / "《影笔代理人》" / "正文"

# ---------- 工具：把文本按"是否在引号内"分段 ----------
# 用 "..." 作为引号对（中文引号）
def split_by_dialogue(text):
    """返回 [(segment, is_dialogue), ...]"""
    parts = []
    # 匹配中文引号 "..."
    pattern = re.compile(r'"[^"]*"')
    last = 0
    for m in pattern.finditer(text):
        if m.start() > last:
            parts.append((text[last:m.start()], False))
        parts.append((m.group(0), True))
        last = m.end()
    if last < len(text):
        parts.append((text[last:], False))
    return parts

# ---------- 破折号处理 ----------
DASH_KEEP_CONTEXT = [
    # 对话中断：——" 或 "—— （话没说完被打断）
]

def fix_dashes(text, target_min=3, target_max=5):
    """精简破折号：保留对话中断/语气突变，其余转逗号"""
    lines = text.split('\n')
    new_lines = []
    # 先收集所有破折号位置
    dash_positions = []  # (line_idx, char_idx_in_line)
    for li, line in enumerate(lines):
        idx = 0
        while True:
            pos = line.find('——', idx)
            if pos == -1:
                break
            dash_positions.append((li, pos, line))
            idx = pos + 2

    total = len(dash_positions)
    if total <= target_max:
        return text  # 已经够少

    # 分类：哪些破折号必须保留
    # 规则：
    # 1. 紧跟在引号后面的（对话中断）——" 或 "——"
    # 2. 位于行首/段首且后面紧跟短 punchline 的
    # 3. 其余转为逗号

    # 标记哪些要保留
    keep = set()
    for i, (li, pos, line) in enumerate(dash_positions):
        # 对话中断：——" 在引号内结尾
        before = line[max(0,pos-3):pos]
        after = line[pos+2:pos+4]
        # 前面是引号结束（话被打断）
        if before.endswith('"') or before.endswith('"'):
            keep.add(i)
        # 后面紧跟引号（话没说完）
        if after.startswith('"') or after.startswith('"'):
            keep.add(i)

    # 如果保留数已经 >= target_min，其余转为逗号
    # 如果保留数 < target_min，再从"解释性破折号"里选几个最有戏剧性的保留
    keep_list = sorted(keep)
    if len(keep_list) < target_min:
        # 从所有非保留破折号里，选后面紧跟短词（<=4字）的保留
        candidates = []
        for i, (li, pos, line) in enumerate(dash_positions):
            if i in keep:
                continue
            after = line[pos+2:pos+8]
            # 找后面第一个标点
            m = re.search(r'[。，！？；：、]', after)
            if m and m.start() <= 4:
                candidates.append(i)
        # 补到 target_min
        need = target_min - len(keep_list)
        for i in candidates[:need]:
            keep.add(i)

    # 执行替换：不在 keep 里的破折号 -> 逗号
    # 从后往前替换，避免位置偏移
    replacements = {}  # line_idx -> list of (pos, replacement)
    for i, (li, pos, line) in enumerate(dash_positions):
        if i not in keep:
            replacements.setdefault(li, []).append(pos)

    for li, positions in replacements.items():
        line = lines[li]
        # 从后往前替换
        for pos in sorted(positions, reverse=True):
            line = line[:pos] + '，' + line[pos+2:]
        lines[li] = line

    return '\n'.join(lines)

# ---------- 断句体合并 ----------
# 这些词后面跟逗号时，逗号通常可以去掉
REMOVABLE_COMMA_AFTER = [
    '然后', '接着', '最后', '后来', '于是', '终于', '这时', '那一刻',
    '下一刻', '下一秒', '紧接着', '紧接着',
]

def fix_commas_in_narration(text):
    """在非对话段落中删除多余的逗号"""
    parts = split_by_dialogue(text)
    result = []
    for seg, is_dialogue in parts:
        if is_dialogue:
            result.append(seg)
            continue
        # 在叙述段落中处理
        new_seg = seg
        # 1. 删除 "然后，" "接着，" 等后面的逗号（在叙述中）
        for w in REMOVABLE_COMMA_AFTER:
            new_seg = new_seg.replace(w + '，', w)
        # 2. 删除 "X了，Y" 中"了，"的逗号（两个动词短语共享主语）
        # 模式：动词+了，动词
        new_seg = re.sub(r'([\u4e00-\u9fff]{1,3})了，([\u4e00-\u9fff]{1,3})着', r'\1了\2着', new_seg)
        # 3. 删除 "抬起头，看着" "低下头，看着" 这类连续动词短语间的逗号
        new_seg = re.sub(r'(抬起头|低下头|转过身|转过头|抬起眼|垂下眼|伸出手|收回手|站起身|坐起身)，', r'\1', new_seg)
        # 4. 删除 "X上，" "X边，" "X里，" 作为句中地点状语后的逗号（但保留段首地点）
        # 注意：只在句中（前面还有字）时删除
        new_seg = re.sub(r'(?<![\n])(桌上|地上|墙上|门口|窗边|巷口|路边|街上|楼梯上)，', r'\1', new_seg)
        # 5. 删除 "X痕，" "X影，" 这类主语后的逗号（短主语+逗号+谓语）
        new_seg = re.sub(r'(墨痕|影子|脚步|目光|声音|呼吸|身体|手指|手背|眼神)，', r'\1', new_seg)
        # 6. 删除 "很X，很Y" 中并列形容词间的逗号 -> 保留（自然停顿，不删）
        # 7. 删除 "X的，Y" 中不必要的逗号（但不删对话标签）
        # 8. 合并 "。X。" 中极短的独立段落（<=3字的独立行）到上一段
        result.append(new_seg)
    return ''.join(result)

def merge_short_paragraphs(text):
    """合并连续的极短段落（<=4字的独立成段）"""
    paragraphs = text.split('\n\n')
    merged = []
    i = 0
    while i < len(paragraphs):
        p = paragraphs[i].strip()
        # 如果当前段很短（<=4字），且不是对话、不是标题
        if (len(p) <= 4 and p and not p.startswith('#')
            and not p.startswith('"') and not p.startswith('"')):
            # 合并到上一段
            if merged:
                merged[-1] = merged[-1].rstrip() + '，' + p + '。'
                # 去掉上一段末尾的句号
                merged[-1] = re.sub(r'。，$', '。', merged[-1])
                merged[-1] = re.sub(r'，' + re.escape(p) + r'。$', '，' + p + '。', merged[-1])
                i += 1
                continue
        merged.append(paragraphs[i])
        i += 1
    return '\n\n'.join(merged)

# ---------- 主流程 ----------
def process_chapter(fpath):
    text = fpath.read_text(encoding='utf-8')
    original = text

    # 1. 破折号精简
    text = fix_dashes(text)

    # 2. 逗号精简（叙述段落）
    text = fix_commas_in_narration(text)

    # 3. 合并极短独立段（暂不启用，风险高）
    # text = merge_short_paragraphs(text)

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
            print(f"  修复: {matches[0].name}")
    print(f"\n共修复 {changed} 章")

if __name__ == '__main__':
    main()
