"""标点滥用检查：检测一章内"单字/双字后紧接标点"异常频繁出现的情况。

判定思路：
- 正常中文写作里，1~2 字后接标点是偶发现象（短停顿、单字句）。
- 如果一章里这种情况出现几十次，说明行文碎、断句过密（"风。雨。雷。电。"式），属于滥用。
- 因此分别统计单字和双字命中数，超过阈值才报警。
"""
import pathlib
import re
import os
import datetime

CST = datetime.timezone(datetime.timedelta(hours=8))
ROOT = pathlib.Path('影笔代理人/正文')
LOG_DIR = pathlib.Path('log')

# 阈值：单字接标点 >= 此数视为异常碎句；双字接标点阈值更高
SINGLE_CHAR_THRESHOLD = 15
DOUBLE_CHAR_THRESHOLD = 30

# 标点集合：句末 + 停顿
PUNCT = r'[。！？；：，、]'

# 单字接标点：一个汉字直接跟标点
SINGLE = re.compile(r'(?<![\u4e00-\u9fa5])[\u4e00-\u9fa5]' + PUNCT)
# 双字接标点：两个汉字直接跟标点（前面不能再有汉字，否则其实是多字词的末尾）
DOUBLE = re.compile(r'(?<![\u4e00-\u9fa5])[\u4e00-\u9fa5]{2}' + PUNCT)

ISSUES = []

for p in sorted(ROOT.rglob('*.md')):
    text = p.read_text(encoding='utf-8', errors='ignore')
    single_hits = SINGLE.findall(text)
    double_hits = DOUBLE.findall(text)
    n_single = len(single_hits)
    n_double = len(double_hits)

    flagged = False
    detail = []
    if n_single >= SINGLE_CHAR_THRESHOLD:
        flagged = True
        detail.append(f"单字接标点 {n_single} 次（阈值 {SINGLE_CHAR_THRESHOLD}）")
    if n_double >= DOUBLE_CHAR_THRESHOLD:
        flagged = True
        detail.append(f"双字接标点 {n_double} 次（阈值 {DOUBLE_CHAR_THRESHOLD}）")

    if flagged:
        # 各举 3 个例子便于人工确认
        examples = []
        for ex in (single_hits[:3] + double_hits[:3]):
            if ex not in examples:
                examples.append(ex)
        ISSUES.append(f"{p}: " + "，".join(detail) + f"；示例：{examples}")

LOG_DIR.mkdir(parents=True, exist_ok=True)
report_file = LOG_DIR / '标点滥用检查.txt'

now = datetime.datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S CST')
content = f"检查时间: {now}\n----------------------------------------\n"
content += f"判定规则：单字接标点 >= {SINGLE_CHAR_THRESHOLD} 次/章，或双字接标点 >= {DOUBLE_CHAR_THRESHOLD} 次/章\n\n"

if ISSUES:
    content += f"共 {len(ISSUES)} 章标点碎句频繁：\n\n" + "\n".join(ISSUES)
    print(f"发现 {len(ISSUES)} 章标点滥用")
    with open(os.environ['GITHUB_ENV'], 'a') as f:
        f.write("HAS_PUNCTUATION_ABUSE=1\n")
else:
    content += "未发现标点滥用问题"
    print("标点滥用检查通过")

report_file.write_text(content, encoding='utf-8')
