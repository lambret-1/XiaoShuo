"""英文标点修正：把正文里误用的英文标点改成中文标点，并写回原文件。

重点处理：
- 英文双引号 " " → 中文 " "（按行交替开闭）
- 英文单引号 ' ' → 中文 ' '（按行交替开闭）
- 英文逗号/句号/问号/叹号/冒号/分号/括号/省略号 → 中文（仅在紧邻中文时替换）
"""
import pathlib
import re
import os
import datetime

CST = datetime.timezone(datetime.timedelta(hours=8))
ROOT = pathlib.Path('影笔代理人/正文')
LOG_DIR = pathlib.Path('log')

# 非引号类规则：(正则, 替换, 名称)
SIMPLE_RULES = [
    (re.compile(r'(?<=[\u4e00-\u9fff]),'), '，', '英文逗号'),
    (re.compile(r',(?=[\u4e00-\u9fff])'), '，', '英文逗号'),
    (re.compile(r'(?<=[\u4e00-\u9fff])\.(?![0-9])'), '。', '英文句号'),
    (re.compile(r'(?<![0-9a-zA-Z])\.(?=[\u4e00-\u9fff])'), '。', '英文句号'),
    (re.compile(r'(?<=[\u4e00-\u9fff])\?'), '？', '英文问号'),
    (re.compile(r'(?<=[\u4e00-\u9fff])!'), '！', '英文叹号'),
    (re.compile(r'(?<=[\u4e00-\u9fff]):'), '：', '英文冒号'),
    (re.compile(r'(?<=[\u4e00-\u9fff]);'), '；', '英文分号'),
    (re.compile(r'\((?=[\u4e00-\u9fff])'), '（', '英文左括号'),
    (re.compile(r'(?<=[\u4e00-\u9fff])\)'), '）', '英文右括号'),
    (re.compile(r'(?<=[\u4e00-\u9fff])\.\.\.(?![.0-9])'), '……', '英文省略号'),
]


def convert_quotes(line: str, quote_char: str, open_q: str, close_q: str):
    """按行交替把英文直引号换成中文弯引号。"""
    result = []
    open_next = True
    for ch in line:
        if ch == quote_char:
            result.append(open_q if open_next else close_q)
            open_next = not open_next
        else:
            result.append(ch)
    return ''.join(result)


changed_chapters = []

for p in sorted(ROOT.glob('第*.md')):
    original = p.read_text(encoding='utf-8')
    new_text = original
    counts = {}
    total = 0

    # 1. 简单标点
    for pattern, repl, label in SIMPLE_RULES:
        new_text, n = pattern.subn(repl, new_text)
        if n > 0:
            counts[label] = counts.get(label, 0) + n
            total += n

    # 2. 双引号 / 单引号（按行处理，避免跨行配对错乱）
    lines = new_text.split('\n')
    new_lines = []
    dq_count = 0
    sq_count = 0
    for line in lines:
        if '"' in line:
            before = line
            line = convert_quotes(line, '"', '“', '”')
            dq_count += before.count('"')
        if "'" in line:
            before = line
            line = convert_quotes(line, "'", '‘', '’')
            sq_count += before.count("'")
        new_lines.append(line)
    new_text = '\n'.join(new_lines)
    if dq_count:
        counts['英文双引号'] = counts.get('英文双引号', 0) + dq_count
        total += dq_count
    if sq_count:
        counts['英文单引号'] = counts.get('英文单引号', 0) + sq_count
        total += sq_count

    if total > 0 and new_text != original:
        p.write_text(new_text, encoding='utf-8')
        detail = '、'.join(f"{k}×{v}" for k, v in counts.items())
        changed_chapters.append(f"{p.name}: 修改 {total} 处（{detail}）")

LOG_DIR.mkdir(parents=True, exist_ok=True)
report_file = LOG_DIR / '英文标点修正.txt'

now = datetime.datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S CST')
lines = [f"检查时间: {now}", '-' * 40, '']

if changed_chapters:
    lines.append(f"共 {len(changed_chapters)} 章发现英文标点符号，已修改为中文标点符号：")
    lines.append('')
    lines.extend(changed_chapters)
    print(f"修正了 {len(changed_chapters)} 章的英文标点，共 {sum(int(c.split('×')[1].split(' ')[0]) for c in [ch.split('（')[1].rstrip('）') for ch in changed_chapters])} 处")
    with open(os.environ['GITHUB_ENV'], 'a') as f:
        f.write("HAS_EN_PUNCT=1\n")
else:
    lines.append("未发现英文标点符号，无需修改。")
    print("英文标点检查通过")

report_file.write_text('\n'.join(lines) + '\n', encoding='utf-8')
