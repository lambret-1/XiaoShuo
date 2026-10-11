#!/usr/bin/env python3
"""
机械修复脚本 v3：第001-100章破折号精简 + 断句体合并
- 破折号：对话中断保留，其余转逗号/句号
- 断句体：激进删除叙述中多余逗号，目标40-60%减少
"""
import os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODY = ROOT / "《影笔代理人》" / "正文"

def split_by_dialogue(text):
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

def fix_dashes(text):
    """破折号处理：
    - 行尾/段尾的—— → 句号（不要留 trailing 逗号）
    - 对话中断的—— → 保留
    - 其余—— → 逗号
    """
    lines = text.split('\n')
    # 收集所有破折号
    dash_info = []  # (line_idx, pos, is_line_end, after_quote, before_quote)
    for li, line in enumerate(lines):
        idx = 0
        while True:
            pos = line.find('——', idx)
            if pos == -1:
                break
            rest = line[pos+2:].strip()
            is_line_end = (rest == '' or rest.startswith('。') or rest.startswith('，'))
            before = line[max(0,pos-3):pos]
            after = line[pos+2:pos+4]
            after_quote = before.endswith('"') or before.endswith('"')
            before_quote = after.startswith('"') or after.startswith('"')
            dash_info.append((li, pos, is_line_end, after_quote, before_quote))
            idx = pos + 2

    if not dash_info:
        return text

    keep_count = sum(1 for d in dash_info if d[3] or d[4])
    total = len(dash_info)
    # 如果保留数已经>=3，其余处理；否则保留前3个最戏剧性的
    keep = set()
    for i, (li, pos, is_end, aq, bq) in enumerate(dash_info):
        if aq or bq:
            keep.add(i)

    # 如果保留数 < 3，再补几个
    if len(keep) < 3:
        for i, d in enumerate(dash_info):
            if i not in keep and not d[2]:
                keep.add(i)
                if len(keep) >= 3:
                    break

    # 执行替换
    replacements = {}  # line_idx -> [(pos, new_str)]
    for i, (li, pos, is_end, aq, bq) in enumerate(dash_info):
        if i in keep:
            continue
        if is_end:
            # 行尾破折号 → 句号（但如果行尾已经是引号结束，保留）
            line = lines[li]
            before = line[:pos]
            # 如果前面是引号内的话，用句号；否则用句号
            replacements.setdefault(li, []).append((pos, '。'))
        else:
            replacements.setdefault(li, []).append((pos, '，'))

    for li, reps in replacements.items():
        line = lines[li]
        for pos, new_str in sorted(reps, key=lambda x: -x[0]):
            line = line[:pos] + new_str + line[pos+2:]
        lines[li] = line

    return '\n'.join(lines)

def remove_commas_narration(text):
    """激进删除叙述段落中的多余逗号"""
    parts = split_by_dialogue(text)
    result = []

    for seg, is_dialogue in parts:
        if is_dialogue:
            result.append(seg)
            continue

        new = seg

        # === 1. 删除常见状语/连接词后的逗号 ===
        new = re.sub(r'(然后|接着|最后|于是|终于|这时|那时|那一刻|下一刻|下一秒|紧接着|后来|随即|立刻|顿时|随即|跟着)，', r'\1', new)

        # === 2. 删除动作短语后的逗号（连续动作共享主语） ===
        new = re.sub(r'(抬起头|低下头|转过身|转过头|转回身|伸出手|收回手|站起身|坐起身|抬起眼|垂下眼|皱起眉|松开手|握紧手|停下脚步|顿了顿|停了停|点点头|摇摇头|叹口气|吸口气|咽了口唾沫|屏住呼吸)，', r'\1', new)

        # === 3. 删除 "X了，Y着" 之间的逗号 ===
        new = re.sub(r'([\u4e00-\u9fff]{1,3})了，([\u4e00-\u9fff]{1,3})着', r'\1了\2着', new)

        # === 4. 删除地点状语后的逗号（句中，非段首） ===
        new = re.sub(r'(?<![\n])(桌上|地上|墙上|门口|窗边|巷口|路边|街上|楼梯上|椅子上|地板上|床上|身上|手上|脸上|眼里|心里|心底|身后|脚下|面前|对面|旁边|一侧)，', r'\1', new)

        # === 5. 删除短主语后的逗号 ===
        new = re.sub(r'(墨痕|影子|脚步|目光|声音|呼吸|身体|手指|手背|眼神|侧脸|身影|轮廓|皮肤|嘴唇|眉头|喉结|瞳孔)，', r'\1', new)

        # === 6. 删除并列形容词间的逗号 "很X，很Y" ===
        new = re.sub(r'(很[\u4e00-\u9fff])，(很[\u4e00-\u9fff])', r'\1\2', new)

        # === 7. 删除副词后的逗号 ===
        new = re.sub(r'(缓慢|慢慢|缓缓|轻轻|静静|默默|微微|淡淡|冷冷|沉沉|渐渐|逐渐)地，', r'\1地', new)

        # === 8. 删除 "，在" "，是" "，像" "，和" "，跟" 前的逗号 ===
        new = re.sub(r'([\u4e00-\u9fff]{1,3})，在([\u4e00-\u9fff])', r'\1在\2', new)
        new = re.sub(r'([\u4e00-\u9fff]{1,3})，是([\u4e00-\u9fff])', r'\1是\2', new)
        new = re.sub(r'([\u4e00-\u9fff]{1,3})，像([\u4e00-\u9fff])', r'\1像\2', new)
        new = re.sub(r'([\u4e00-\u9fff]{1,3})，(和|跟|与|及)([\u4e00-\u9fff])', r'\1\2\3', new)

        # === 9. 删除 "，看着" "，听着" "，想着" "，说着" "，走着" "，站着" "，坐着" 前的逗号 ===
        # （连续动作，共享主语）
        new = re.sub(r'([\u4e00-\u9fff]{1,3})，(看着|听着|想着|说着|走着|站着|坐着|盯着|望着|瞧着) ', r'\1\2 ', new)
        new = re.sub(r'([\u4e00-\u9fff]{1,3})，(看着|听着|想着|说着|走着|站着|坐着|盯着|望着|瞧着)([\u4e00-\u9fff])', r'\1\2\3', new)

        # === 10. 删除 "，没有" "，不" 前的逗号（连续否定） ===
        new = re.sub(r'([\u4e00-\u9fff]{1,3})，没有([\u4e00-\u9fff])', r'\1没有\2', new)
        new = re.sub(r'([\u4e00-\u9fff]{1,3})，不([\u4e00-\u9fff])', r'\1不\2', new)

        # === 11. 删除 "，画出" "，拿出" "，放下" "，拿起" "，推开" "，拉过" 前的逗号 ===
        new = re.sub(r'([\u4e00-\u9fff]{1,3})，(画出|拿出|放下|拿起|推开|拉过|取出|掏出|递过|接过|翻开|合上|写下|画下) ', r'\1\2 ', new)
        new = re.sub(r'([\u4e00-\u9fff]{1,3})，(画出|拿出|放下|拿起|推开|拉过|取出|掏出|递过|接过|翻开|合上|写下|画下)([\u4e00-\u9fff])', r'\1\2\3', new)

        # === 12. 删除 "，声音" "，目光" "，表情" 前的逗号（描述人物） ===
        new = re.sub(r'([\u4e00-\u9fff]{1,3})，(声音|目光|表情|脸色|眼神|嘴角|眉头)([\u4e00-\u9fff])', r'\1\2\3', new)

        # === 13. 删除段尾多余逗号（上一行 dash 转换留下的） ===
        new = re.sub(r'，\n', '\n', new)

        result.append(new)

    return ''.join(result)

def process_chapter(fpath):
    text = fpath.read_text(encoding='utf-8')
    original = text
    text = fix_dashes(text)
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
