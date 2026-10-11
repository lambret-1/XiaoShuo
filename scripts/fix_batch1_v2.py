#!/usr/bin/env python3
"""
机械修复脚本 v2：第001-100章破折号精简 + 断句体合并
更激进地删除叙述中多余的逗号，目标减少40-60%断句体命中
"""
import os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODY = ROOT / "《影笔代理人》" / "正文"

# ---------- 把文本按"是否在中文引号内"分段 ----------
def split_by_dialogue(text):
    """返回 [(segment, is_dialogue), ...]"""
    parts = []
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
def fix_dashes(text):
    """精简破折号：保留对话中断，其余转逗号（后续逗号删除会进一步处理）"""
    lines = text.split('\n')
    dash_positions = []
    for li, line in enumerate(lines):
        idx = 0
        while True:
            pos = line.find('——', idx)
            if pos == -1:
                break
            dash_positions.append((li, pos))
            idx = pos + 2

    if len(dash_positions) <= 4:
        return text

    # 保留：对话中断（——紧跟引号）
    keep = set()
    for i, (li, pos) in enumerate(dash_positions):
        line = lines[li]
        before = line[max(0, pos-2):pos]
        after = line[pos+2:pos+4]
        if before.endswith('"') or before.endswith('"'):
            keep.add(i)
        if after.startswith('"') or after.startswith('"'):
            keep.add(i)

    # 其余全部转为逗号
    replacements = {}
    for i, (li, pos) in enumerate(dash_positions):
        if i not in keep:
            replacements.setdefault(li, []).append(pos)

    for li, positions in replacements.items():
        line = lines[li]
        for pos in sorted(positions, reverse=True):
            line = line[:pos] + '，' + line[pos+2:]
        lines[li] = line

    return '\n'.join(lines)

# ---------- 逗号精简（仅叙述段落） ----------
def remove_commas_narration(text):
    """在非对话段落中删除多余逗号"""
    parts = split_by_dialogue(text)
    result = []

    # 不应删除逗号的模式（保护）：
    # - 对话标签：X说，/X道，/X问，/X答，
    # - 称呼：X，你/您/我...
    # - 时间从句：的时候，/之后，/以前，/以前，/后来，/此时，/那时，
    # - 句首场景：画室里，/窗外，/门口，（段首第一个逗号保留）

    KEEP_COMMA_AFTER = [
        '的时候', '之后', '以前', '以来', '为止',
        '他说', '她说', '我说', '你说', '沈砚说', '周明说', '苏听晚说',
        '他道', '她道', '沈砚道', '他问', '她问', '他答',
        '开口', '低声', '沉声', '轻声', '淡淡',
    ]

    for seg, is_dialogue in parts:
        if is_dialogue:
            result.append(seg)
            continue

        new = seg

        # 1. 删除 "然后，" "接着，" "最后，" "于是，" "终于，" "这时，" 等
        new = re.sub(r'(然后|接着|最后|于是|终于|这时|那时|那一刻|下一刻|下一秒|紧接着|后来|随即|立刻|顿时)，', r'\1', new)

        # 2. 删除连续动作之间的逗号：动词短语+，+动词短语
        # 模式：(抬起头|低下头|转过身|转过头|伸出手|收回手|站起身|坐起身|抬起眼|垂下眼|皱起眉|松开手|握紧手|停下步|转回身)，
        new = re.sub(r'(抬起头|低下头|转过身|转过头|转回身|伸出手|收回手|站起身|坐起身|抬起眼|垂下眼|皱起眉|松开手|握紧手|停下脚步|顿了顿|停了停)，', r'\1', new)

        # 3. 删除 "X了，Y着" 之间的逗号（两个动词短语共享主语）
        new = re.sub(r'([\u4e00-\u9fff]{1,3})了，([\u4e00-\u9fff]{1,3})着', r'\1了\2着', new)

        # 4. 删除 "X上，" "X里，" "X边，" 作为句中地点状语的逗号
        # 但保留段首（前面是换行）的地点逗号
        new = re.sub(r'(?<![\n])(桌上|地上|墙上|门口|窗边|巷口|路边|街上|楼梯上|椅子上|地板上|床上|身上|手上|脸上|眼里|心里|心底)，', r'\1', new)

        # 5. 删除短主语后的逗号：墨痕，/影子，/脚步，/目光，/声音，/呼吸，/身体，/手指，/手背，/眼神，
        new = re.sub(r'(墨痕|影子|脚步|目光|声音|呼吸|身体|手指|手背|眼神|侧脸|身影|轮廓|皮肤|嘴唇|眉头)，', r'\1', new)

        # 6. 删除 "很X，很Y" 并列形容词间的逗号（在叙述中）
        new = re.sub(r'(很[\u4e00-\u9fff])，(很[\u4e00-\u9fff])', r'\1\2', new)

        # 7. 删除 "X的，Y" 中不必要的逗号（但不删对话标签）
        # 模式：形容词/副词+的，+动词
        new = re.sub(r'(缓慢|慢慢|缓缓|轻轻|静静|默默|微微|淡淡|冷冷|沉沉)地，', r'\1地', new)

        # 8. 删除 "，在" 前面的逗号（动词+在+地点）
        new = re.sub(r'([\u4e00-\u9fff]{1,3})，在([\u4e00-\u9fff])', r'\1在\2', new)

        # 9. 删除 "，是" 前面的逗号（判断句）
        new = re.sub(r'([\u4e00-\u9fff]{1,3})，是([\u4e00-\u9fff])', r'\1是\2', new)

        # 10. 删除 "，像" 前面的逗号（比喻句）
        new = re.sub(r'([\u4e00-\u9fff]{1,3})，像([\u4e00-\u9fff])', r'\1像\2', new)

        # 11. 删除 "，和" "，跟" "，与" 前面的逗号
        new = re.sub(r'([\u4e00-\u9fff]{1,3})，(和|跟|与|及)([\u4e00-\u9fff])', r'\1\2\3', new)

        # 12. 删除 "，但" "，可" "，却" "，而" 前面的逗号（转折太密时）
        # 暂不删除，保留转折语气

        # 13. 删除 "X了。Y" 中句号后的短词合并（独立成段的极短句）
        # 暂不处理，风险高

        result.append(new)

    return ''.join(result)

# ---------- 主流程 ----------
def process_chapter(fpath):
    text = fpath.read_text(encoding='utf-8')
    original = text

    # 1. 破折号精简
    text = fix_dashes(text)

    # 2. 逗号精简
    text = remove_commas_narration(text)

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
