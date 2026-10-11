"""破折号检测：单章破折号超过 2 个即报。"""
import pathlib
import re
import os
import datetime

ROOT = pathlib.Path('影笔代理人')
ISSUES = []

for p in sorted(ROOT.rglob('*.md')):
    text = p.read_text(encoding='utf-8', errors='ignore')
    dashes = re.findall(r'—+', text)
    if len(dashes) > 2:
        ISSUES.append(f"{p}: 本章共发现 {len(dashes)} 个破折号")

bug_dir = pathlib.Path('bug')
bug_dir.mkdir(exist_ok=True)
report_file = bug_dir / 'dash.txt'

now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
content = f"检查时间: {now}\n----------------------------------------\n"

if ISSUES:
    content += "\n".join(ISSUES)
    print(f"发现 {len(ISSUES)} 个文件破折号过多")
    with open(os.environ['GITHUB_ENV'], 'a') as f:
        f.write("HAS_DASH=1\n")
else:
    content += "未发现破折号过多的问题"
    print("破折号检测通过")

report_file.write_text(content, encoding='utf-8')
