#!/usr/bin/env python3
"""
机械修复脚本 v4：第001-100章
- 破折号：对话中断保留，其余转逗号/句号
- 断句体：激进删除叙述中多余逗号
- 保护：对话标签、对话间动作拍、转折连词、平行结构
"""
import os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODY = ROOT / "《影笔代理人》" / "正文"

def split_segments(text):
    """把文本分成段，标注是否在对话内或对话拍中
    返回 [(text, mode)]，mode: 'narration' | 'dialogue' | 'beat'
    'beat' = 两个引号之间的动作描写（保护）
    """
    parts = []
    # 匹配 "..." 引号对
    pattern = re.compile(r'"[^"]*"')
    last = 0
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        if m.start() > last:
            seg = text[last:m.start()]
            # 如果前一个段是引号，且当前段很短（动作拍），保护
            if i > 0 and len(seg.strip()) < 40:
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

    # 保留到3个
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

def remove_commas(seg, is_narration):
    """在叙述段落中删除多余逗号"""
    if not is_narration:
        return seg

    new = seg

    # === 保护对话标签：X说，X道，X问，X答，X开口，X低声说，等 ===
    # 先把这些标签临时替换成占位符
    dialogue_tags = []
    def protect_tag(m):
        dialogue_tags.append(m.group(0))
        return f'__TAG{len(dialogue_tags)-1}__'
    new = re.sub(r'[\u4e00-\u9fff]{1,4}(?:说|道|问|答|开口|低声|沉声|轻声|淡淡|冷冷|笑着|叹道|问道|答道|回道|接道|补充道)，', protect_tag, new)

    # === 保护转折连词前的逗号 ===
    def protect_turn(m):
        dialogue_tags.append(m.group(0))
        return f'__TAG{len(dialogue_tags)-1}__'
    new = re.sub(r'，(?:但|但是|可|可是|却|而|然而|不过|只是|就是)', protect_turn, new)

    # === 保护时间从句 ===
    new = re.sub(r'的时候，', protect_turn, new)
    new = re.sub(r'(?:之后|以前|以来|为止|同时|当时|那时)，', protect_turn, new)

    # === 1. 删除状语/连接词后的逗号 ===
    new = re.sub(r'(然后|接着|最后|于是|终于|这时|那一刻|下一刻|下一秒|紧接着|后来|随即|立刻|顿时|跟着|随即)，', r'\1', new)

    # === 2. 删除动作短语后的逗号 ===
    new = re.sub(r'(抬起头|低下头|转过身|转过头|转回身|伸出手|收回手|站起身|坐起身|抬起眼|垂下眼|皱起眉|松开手|握紧手|停下脚步|顿了顿|停了停|点点头|摇摇头|叹口气|吸口气|咽了口唾沫|屏住呼吸)，', r'\1', new)

    # === 3. 删除 "X了，Y着" ===
    new = re.sub(r'([\u4e00-\u9fff]{1,3})了，([\u4e00-\u9fff]{1,3})着', r'\1了\2着', new)

    # === 4. 删除地点状语后的逗号（句中） ===
    new = re.sub(r'(?<![\n])(桌上|地上|墙上|门口|窗边|巷口|路边|街上|楼梯上|椅子上|地板上|床上|身上|手上|脸上|眼里|心里|心底|身后|脚下|面前|对面|旁边|一侧|原地)，', r'\1', new)

    # === 5. 删除短主语后的逗号 ===
    new = re.sub(r'(墨痕|影子|脚步|目光|声音|呼吸|身体|手指|手背|眼神|侧脸|身影|轮廓|皮肤|嘴唇|眉头|喉结|瞳孔|脸色|嘴角)，', r'\1', new)

    # === 6. 删除 "很X，很Y" ===
    new = re.sub(r'(很[\u4e00-\u9fff])，(很[\u4e00-\u9fff])', r'\1\2', new)

    # === 7. 删除副词后的逗号 ===
    new = re.sub(r'(缓慢|慢慢|缓缓|轻轻|静静|默默|微微|淡淡|冷冷|沉沉|渐渐|逐渐)地，', r'\1地', new)

    # === 8. 删除 "，在" "，是" "，像" "，和/跟/与" ===
    new = re.sub(r'([\u4e00-\u9fff]{1,3})，在([\u4e00-\u9fff])', r'\1在\2', new)
    new = re.sub(r'([\u4e00-\u9fff]{1,3})，是([\u4e00-\u9fff])', r'\1是\2', new)
    new = re.sub(r'([\u4e00-\u9fff]{1,3})，像([\u4e00-\u9fff])', r'\1像\2', new)
    new = re.sub(r'([\u4e00-\u9fff]{1,3})，(和|跟|与|及)([\u4e00-\u9fff])', r'\1\2\3', new)

    # === 9. 删除 "，看着/听着/想着/说着/走着/站着/坐着/盯着" ===
    new = re.sub(r'([\u4e00-\u9fff]{1,3})，(看着|听着|想着|说着|走着|站着|坐着|盯着|望着|瞧着)([\u4e00-\u9fff])', r'\1\2\3', new)

    # === 10. 删除 "，没有" "，不" ===
    new = re.sub(r'([\u4e00-\u9fff]{1,3})，没有([\u4e00-\u9fff])', r'\1没有\2', new)
    # 不删除 "，不" 因为会破坏平行结构（不惊讶，不同情，不劝你）

    # === 11. 删除 "，画出/拿出/放下/拿起/推开/取出/掏出/递过/接过/翻开/合上" ===
    new = re.sub(r'([\u4e00-\u9fff]{1,3})，(画出|拿出|放下|拿起|推开|拉过|取出|掏出|递过|接过|翻开|合上|写下|画下|按下|抓起|扔掉|塞进|递上)([\u4e00-\u9fff])', r'\1\2\3', new)

    # === 12. 删除 "，声音/目光/表情/脸色/眼神/嘴角/眉头" 前的逗号 ===
    # 但保护对话标签（已被占位符保护）
    new = re.sub(r'([\u4e00-\u9fff]{1,3})，(声音|目光|表情|脸色|眼神|嘴角|眉头)([\u4e00-\u9fff])', r'\1\2\3', new)

    # === 13. 删除段尾多余逗号 ===
    new = re.sub(r'，\n', '\n', new)
    new = re.sub(r'。，', '。', new)

    # === 恢复被保护的标签 ===
    for i, tag in enumerate(dialogue_tags):
        new = new.replace(f'__TAG{i}__', tag)

    return new

def process_chapter(fpath):
    text = fpath.read_text(encoding='utf-8')
    original = text
    text = fix_dashes(text)

    # 分段处理逗号
    segments = split_segments(text)
    new_segments = []
    for seg, mode in segments:
        if mode == 'narration':
            new_segments.append(remove_commas(seg, True))
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
