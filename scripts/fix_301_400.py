#!/usr/bin/env python3
"""
第301-400章断句体保守修复脚本
原则：
- 保留高潮/紧张/情绪段的断句节奏
- 仅合并非高潮叙述段中明显过度的逗号断句
- 对话、短节拍段、诗化单字段全部保留
- 破折号精简到每章3-5个
"""
import os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BODY = ROOT / "《影笔代理人》" / "正文"

# 中文引号
LQ = '\u201c'  # "
RQ = '\u201d'  # "

def is_section_sep(line):
    s = line.strip()
    return s == "---" or s == "***" or s == "___"

def has_dialogue(line):
    """含中文引号的行，认为是对话/引语，整体保留断句"""
    return (LQ in line) or (RQ in line) or ('"' in line) or ("「" in line) or ("『" in line)

def chinese_char_count(s):
    return len(re.findall(r'[\u4e00-\u9fff]', s))

def is_poetic_period_style(para):
    """检测是否为诗化/高潮的句号断句体（如"周。是，三，天。"）
    特征：按句号切分后，多数片段很短（<=5个中文字），说明句号在句中断开
    """
    # 去掉引号内容
    text = re.sub(LQ + r'[^' + RQ + LQ + r']*' + RQ, '', para)
    # 按句号、问号、感叹号切分
    sentences = re.split(r'[。！？]', text)
    sentences = [s for s in sentences if s.strip()]
    if len(sentences) < 3:
        return False
    # 统计每个句子的中文字数
    lengths = [chinese_char_count(s) for s in sentences]
    short_count = sum(1 for l in lengths if l <= 5)
    # 如果>=3个句子且多数短句，认为是诗化体
    if len(sentences) >= 3 and short_count >= len(sentences) * 0.7:
        return True
    return False

def is_short_beat(para):
    """短节拍段（<10个中文字符），认为是戏剧节拍，保留"""
    return chinese_char_count(para) < 10

def merge_commas_in_para(para):
    """对段落合并过度的逗号断句。
    注意：句号/感叹号/问号的断句是高潮节奏，保留不动；
    仅合并逗号连接的短片段（包括诗化段落内部的逗号）。
    """
    if has_dialogue(para):
        return para
    if is_short_beat(para):
        return para
    chars = chinese_char_count(para)
    if chars < 12:
        return para
    # 含英文/数字的段落保守不处理
    if re.search(r'[a-zA-Z0-9]', para):
        return para

    parts = re.findall(r'([\u4e00-\u9fff]+)([，。！？；：、])', para)
    if not parts:
        return para

    merged = []
    i = 0
    while i < len(parts):
        cur_text, cur_punct = parts[i]
        # 仅当当前标点是逗号时，尝试与下一个片段合并
        if cur_punct == '，' and i + 1 < len(parts):
            next_text, next_punct = parts[i+1]
            combined_len = len(cur_text) + len(next_text)
            can_merge = (
                (len(cur_text) <= 3 and len(next_text) <= 3 and combined_len <= 6) or
                (len(cur_text) <= 4 and len(next_text) <= 3 and combined_len <= 7) or
                (len(cur_text) <= 3 and len(next_text) <= 4 and combined_len <= 7)
            )
            if can_merge:
                merged.append((cur_text + next_text, next_punct))
                i += 2
                continue
        merged.append((cur_text, cur_punct))
        i += 1

    result = ''.join(t + p for t, p in merged)
    return result

def reduce_dashes(text, target=4):
    """将破折号——精简到target个以内。"""
    positions = [m.start() for m in re.finditer(r'——', text)]
    if len(positions) <= target:
        return text
    # 保留前target个，其余替换为句号
    replace_positions = positions[target:]
    chars = list(text)
    for pos in reversed(replace_positions):
        chars[pos:pos+2] = ['。', '']
    result = ''.join(chars)
    result = re.sub(r'。{2,}', '。', result)
    result = result.replace(LQ + '。', LQ)
    return result

def process_chapter(ch_num):
    pattern = f"第{ch_num:03d}章*.md"
    matches = list(BODY.glob(pattern))
    if not matches:
        pattern = f"第{ch_num}章*.md"
        matches = list(BODY.glob(pattern))
    if not matches:
        return None, "not found"
    fpath = matches[0]
    text = fpath.read_text(encoding="utf-8")
    orig = text

    dash_count = text.count("——")
    if dash_count > 5:
        text = reduce_dashes(text, target=4)

    paragraphs = text.split('\n\n')
    new_paragraphs = []
    for para in paragraphs:
        stripped = para.strip()
        if is_section_sep(stripped) or not stripped:
            new_paragraphs.append(para)
            continue
        new_para = merge_commas_in_para(para)
        new_paragraphs.append(new_para)
    text = '\n\n'.join(new_paragraphs)

    if text != orig:
        fpath.write_text(text, encoding="utf-8")
        return fpath.name, "modified"
    return fpath.name, "skipped"

def main():
    if len(sys.argv) < 3:
        print("用法: python3 fix_301_400.py <start> <end>")
        sys.exit(1)
    start = int(sys.argv[1])
    end = int(sys.argv[2])
    modified = []
    skipped = []
    for ch in range(start, end+1):
        name, status = process_chapter(ch)
        if status == "modified":
            modified.append(ch)
        elif status == "skipped":
            skipped.append(ch)
    print(f"修改: {len(modified)} 章")
    print(f"跳过(无需改): {len(skipped)} 章")
    if modified:
        print(f"修改章节: {modified[:30]}{'...' if len(modified)>30 else ''}")

if __name__ == "__main__":
    main()
