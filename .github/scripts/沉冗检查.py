"""沉冗检查：段落过长、重复表达。输出 log/沉冗检查.txt（覆盖）。"""
import pathlib
import re
import os
import datetime

CST = datetime.timezone(datetime.timedelta(hours=8))
ROOT = pathlib.Path('影笔代理人')
LOG_DIR = pathlib.Path('log')
MAX_LEN = 200
ISSUES = []

for p in sorted(ROOT.rglob('*.md')):
    text = p.read_text(encoding='utf-8', errors='ignore')
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        if len(s) > MAX_LEN:
            ISSUES.append(f"{p}:{i}: 段落过长（{len(s)} 字）")
        match = re.search(r'(.{2,6})\1{2,}', s)
        if match:
            ISSUES.append(f"{p}:{i}: 疑似重复表达（重复内容：'{match.group(0)}'）")

LOG_DIR.mkdir(parents=True, exist_ok=True)
report_file = LOG_DIR / '沉冗检查.txt'

now = datetime.datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S CST')
content = f"检查时间: {now}\n----------------------------------------\n"

if ISSUES:
    content += "\n".join(ISSUES)
    print("发现沉冗或重复内容，已写入", report_file)
    with open(os.environ['GITHUB_ENV'], 'a') as f:
        f.write("HAS_REDUNDANCY=1\n")
else:
    content += "未发现沉冗问题"
    print("沉冗检查通过。")

report_file.write_text(content, encoding='utf-8')
