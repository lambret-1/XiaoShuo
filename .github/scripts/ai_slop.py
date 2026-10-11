"""反 AI 味检测：模板句式、空洞修饰、总结词、翻译腔、陈词滥调。"""
import pathlib
import re
import os
import datetime

ROOT = pathlib.Path('影笔代理人')
ISSUES = []

RULES = [
    ("模板句式-不是而是", r'不是.{1,20}，?而是', "AI 常见对比句式"),
    ("模板句式-与其不如", r'与其说.{1,20}，?不如说', "AI 常见对比句式"),
    ("模板句式-不仅更是", r'不仅.{1,20}，?更是', "AI 常见递进句式"),
    ("模板句式-既又", r'既.{1,15}，?又.{1,15}，?', "AI 常见并列句式"),
    ("模板句式-既是也是", r'既是.{1,15}，?也是', "AI 常见并列句式"),
    ("空洞修饰-某种程度", r'在?某种(程度|意义|角度)上', "AI 常用的模糊修饰"),
    ("空洞修饰-某种意义", r'从某种(程度|意义|角度)(来|上)(说|讲)', "AI 常用的模糊修饰"),
    ("空洞修饰-可以说", r'可以说[，,]', "AI 常用的空话开头"),
    ("空洞修饰-不得不说是", r'不得不说是', "AI 常用的评述句"),
    ("总结词-总而言之", r'总而言之[，,]', "AI 常用的总结句"),
    ("总结词-综上所述", r'综上所述[，,]', "AI 常用的总结句"),
    ("总结词-总的来说", r'总的来说[，,]', "AI 常用的总结句"),
    ("总结词-值得注意的是", r'值得注意的是[，,]', "AI 常用的提示句"),
    ("总结词-需要指出的是", r'需要指出的是[，,]', "AI 常用的提示句"),
    ("总结词-换句话说", r'换句话(来)?说[，,]', "AI 常用的重复解释"),
    ("总结词-也就是说", r'也就是说[，,]', "AI 常用的重复解释"),
    ("翻译腔-作为一个", r'作为一个.{1,15}[，,]', "AI 常见的翻译腔句式"),
    ("翻译腔-对于而言", r'对于.{1,15}(来)?(说|讲)[，,]', "AI 常见的翻译腔句式"),
    ("翻译腔-关于这个问题", r'关于这个问题[，,]', "AI 常见的翻译腔句式"),
    ("翻译腔-在某种程度上", r'在某种程度上[，,]', "AI 常见的翻译腔句式"),
    ("过度连接-然而", r'^然而[，,]', "AI 常用的连接词开头"),
    ("过度连接-因此", r'^因此[，,]', "AI 常用的连接词开头"),
    ("过度连接-此外", r'^此外[，,]', "AI 常用的连接词开头"),
    ("过度连接-另外", r'^另外[，,]', "AI 常用的连接词开头"),
    ("陈词滥调-不禁", r'不禁.{1,10}起来', "AI 常见的套路句"),
    ("陈词滥调-油然而生", r'油然而生', "AI 常见的套路句"),
    ("陈词滥调-涌上心头", r'涌上心头', "AI 常见的套路句"),
    ("陈词滥调-五味杂陈", r'五味杂陈', "AI 常见的套路句"),
    ("陈词滥调-心潮澎湃", r'心潮澎湃', "AI 常见的套路句"),
]

for p in sorted(ROOT.rglob('*.md')):
    text = p.read_text(encoding='utf-8', errors='ignore')
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        for rule_name, pattern, desc in RULES:
            match = re.search(pattern, s)
            if match:
                ISSUES.append(f"{p}:{i}: [{rule_name}] {desc}（命中：'{match.group(0)}'）")

bug_dir = pathlib.Path('bug')
bug_dir.mkdir(exist_ok=True)
report_file = bug_dir / 'ai_slop.txt'

now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
content = f"检查时间: {now}\n----------------------------------------\n"

if ISSUES:
    content += f"共发现 {len(ISSUES)} 处 AI 写作特征：\n\n"
    content += "\n".join(ISSUES)
    print(f"发现 {len(ISSUES)} 处 AI 写作特征")
    with open(os.environ['GITHUB_ENV'], 'a') as f:
        f.write("HAS_AISLOP=1\n")
else:
    content += "未检测到 AI 写作特征"
    print("反 AI 味检测通过")

report_file.write_text(content, encoding='utf-8')
