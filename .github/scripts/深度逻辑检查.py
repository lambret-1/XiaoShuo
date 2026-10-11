#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《影笔代理人》深度逻辑检查
输出：log/深度逻辑检查.txt、log/章节统计.txt、log/合规校验.txt
"""
import os
import re
import json
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NOVEL = ROOT / "影笔代理人"
BODY = NOVEL / "正文"
CONTINUITY = NOVEL / "连续性"
LOG = ROOT / "log"

MIN_WORDS = 1500
MAX_WORDS = 5000
MIN_TITLE_LEN = 3
MAX_TITLE_LEN = 15
FORESHADOW_ACTIVE_LIMIT = 50

errors = []
warnings = []
info_logs = []

def err(msg): errors.append(msg)
def warn(msg): warnings.append(msg)
def info(msg): info_logs.append(msg)

chapters = {}
if BODY.exists():
    for p in BODY.glob("第*.md"):
        m = re.match(r"第(\d{3})章\s+(.+)\.md", p.name)
        if m:
            num = int(m.group(1))
            with open(p, encoding="utf-8") as f:
                chapters[num] = {"title": m.group(2), "content": f.read()}

max_chapter = max(chapters.keys()) if chapters else 0
print(f">>> 深度检查，已加载章节 {len(chapters)}")

title_repeats = {}
for num, d in chapters.items():
    wc = len(re.sub(r'\s', '', d["content"]))
    if wc < MIN_WORDS:
        warn(f"第{num:03d}章《{d['title']}》字数过少 ({wc}字)")
    elif wc > MAX_WORDS:
        warn(f"第{num:03d}章《{d['title']}》字数过多 ({wc}字)")
    t = d["title"]
    if len(t) < MIN_TITLE_LEN:
        warn(f"第{num:03d}章标题《{t}》过短")
    if len(t) > MAX_TITLE_LEN:
        warn(f"第{num:03d}章标题《{t}》过长")
    if t in title_repeats:
        warn(f"第{num:03d}章标题《{t}》与第{title_repeats[t]:03d}章重复")
    else:
        title_repeats[t] = num

fs_file = CONTINUITY / "伏笔.yaml"
if fs_file.exists():
    fs_data = yaml.safe_load(fs_file)
    def chk_fs(obj, path=""):
        if isinstance(obj, dict):
            if "status" in obj and "chapter" in obj:
                try:
                    ch = int(obj["chapter"])
                    if obj["status"] == "active" and max_chapter - ch > FORESHADOW_ACTIVE_LIMIT:
                        warn(f"伏笔 {path} 活跃超过{FORESHADOW_ACTIVE_LIMIT}章")
                except ValueError:
                    pass
            for k, v in obj.items(): chk_fs(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj): chk_fs(v, f"{path}[{i}]")
        elif isinstance(obj, str):
            for m in re.finditer(r"(?:第)?(\d{3})\s*(?:[-–~]\s*(\d{3}))?", obj):
                s = int(m.group(1)); e = int(m.group(2)) if m.group(2) else s
                for n in range(s, e + 1):
                    if n <= max_chapter and n not in chapters:
                        err(f"伏笔引用了不存在的第{n:03d}章")
    chk_fs(fs_data)

char_file = CONTINUITY / "人物.yaml"
if char_file.exists() and chapters:
    char_data = yaml.safe_load(char_file)
    names = set()
    def ext(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "characters" and isinstance(v, dict): names.update(v.keys())
                if k == "name" and isinstance(v, str): names.add(v)
                ext(v)
        elif isinstance(o, list):
            for v in o: ext(v)
    ext(char_data)
    for n in names:
        hit = [num for num, d in chapters.items() if n in d["content"]]
        if hit:
            info(f"角色 '{n}' 出现在 第{min(hit):03d}~第{max(hit):03d}章")
        else:
            warn(f"人物 '{n}' 在正文中未出现")

tl_file = CONTINUITY / "时间线.yaml"
if tl_file.exists():
    tl = yaml.safe_load(tl_file)
    def chk_tl(obj, path=""):
        if isinstance(obj, dict):
            if "start" in obj and "end" in obj:
                try:
                    if int(obj["start"]) > int(obj["end"]):
                        err(f"时间线 {path} start({obj['start']}) > end({obj['end']})")
                except ValueError:
                    pass
            for k, v in obj.items(): chk_tl(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj): chk_tl(v, f"{path}[{i}]")
    chk_tl(tl)

wsc = LOG / "WSC风格报告.json"
if wsc.exists():
    try:
        d = json.load(open(wsc, encoding="utf-8"))
        n = d.get("summary", {}).get("warnings", 0) if isinstance(d, dict) else len(d)
        if n > 20:
            warn(f"WSC 发现 {n} 个风格问题")
    except Exception as e:
        warn(f"WSC 报告解析失败: {e}")

LOG.mkdir(exist_ok=True)
with open(LOG / "深度逻辑检查.txt", "w", encoding="utf-8") as f:
    f.write(f"=== 错误 ({len(errors)}) ===\n")
    for e in errors: f.write(f"  - {e}\n")
    f.write(f"\n=== 警告 ({len(warnings)}) ===\n")
    for w in warnings: f.write(f"  - {w}\n")
    f.write(f"\n=== 信息 ({len(info_logs)}) ===\n")
    for i in info_logs: f.write(f"  - {i}\n")

total_words = sum(len(re.sub(r'\s', '', d["content"])) for d in chapters.values())
with open(LOG / "章节统计.txt", "w", encoding="utf-8") as f:
    f.write(f"《影笔代理人》统计报告\n总章节数: {len(chapters)}\n总字数(去除空白): {total_words}\n")

with open(LOG / "合规校验.txt", "w", encoding="utf-8") as f:
    f.write(f"合规检查未通过，{len(errors)} 个错误。\n" if errors else "合规检查通过，未发现目录/引用错误。\n")
