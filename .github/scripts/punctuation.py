"""标点滥用检查：单字/双字后紧接标点。报告写入 bug/punctuation_abuse.txt（覆盖）。"""
import pathlib
import re
import os
import datetime

CST = datetime.timezone(datetime.timedelta(hours=8))
ROOT = pathlib.Path('影笔代理人')
BUG_DIR = pathlib.Path('bug')
ISSUES = []

PATTERN = re.compile(r'[\u4e00-\u9fa5](?:[\u4e00-\u9fa5])?[。！？；：，、]')

for p in sorted(ROOT.rglob('*.md')):
    text = p.read_text(encoding='utf-8', errors='ignore')
    matches = PATTERN.findall(text)
    count = len(matches)
    if count > 10:
        ISSUES.append(f"{p}: 本章共发现 {count} 处单字/双字后紧接标点")

BUG_DIR.mkdir(exist_ok=True)
report_file = BUG_DIR / 'punctuation_abuse.txt'

now = datetime.datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S CST')
content = f"检查时间: {now}\n----------------------------------------\n"

if ISSUES:
    total = len(ISSUES)
    content += f"总共发现了 {total} 章滥用内容，以下是具体章节：\n\n"
    content += "\n".join(ISSUES)
    print(f"发现 {total} 章滥用标点符号")
    with open(os.environ['GITHUB_ENV'], 'a') as f:
        f.write("HAS_PUNCTUATION_ABUSE=1\n")
else:
    content += "未发现标点滥用问题"
    print("标点滥用检查通过")

report_file.write_text(content, encoding='utf-8')
