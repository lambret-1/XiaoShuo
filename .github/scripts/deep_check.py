#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《影笔代理人》深度逻辑检查脚本
输出：log/深度检查.txt、log/story_stats.txt、log/story_validate.txt
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

# 配置阈值
MIN_WORDS = 1500
MAX_WORDS = 5000
MIN_TITLE_LEN = 3
MAX_TITLE_LEN = 15
FORESHADOW_ACTIVE_LIMIT = 50  # 伏笔活跃超过多少章未更新报警

errors = []
warnings = []
info_logs = []

def err(msg): errors.append(msg)
def warn(msg): warnings.append(msg)
def info(msg): info_logs.append(msg)

# 读取章节文件
chapters = {}
if BODY.exists():
    for p in BODY.glob("第*.md"):
        m = re.match(r"第(\d{3})章\s+(.+)\.md", p.name)
        if m:
            num = int(m.group(1))
            title = m.group(2)
            with open(p, encoding="utf-8") as f:
                content = f.read()
            chapters[num] = {"title": title, "content": content, "path": p.name}

max_chapter = max(chapters.keys()) if chapters else 0

print(">>> 开始《影笔代理人》深度检查...")
print(f"    目录: {NOVEL}")
print(f"    已加载章节: {len(chapters)}")

# ================= 1. 字数与标题检查 =================
print("  >>> 检查字数与标题...")
title_repeats = {}
for num, data in chapters.items():
    pure_text = re.sub(r'\s', '', data["content"])
    word_count = len(pure_text)
    if word_count < MIN_WORDS:
        warn(f"第{num:03d}章《{data['title']}》字数过少 ({word_count}字)，低于 {MIN_WORDS} 字")
    elif word_count > MAX_WORDS:
        warn(f"第{num:03d}章《{data['title']}》字数过多 ({word_count}字)，超过 {MAX_WORDS} 字")

    title = data["title"]
    if len(title) < MIN_TITLE_LEN:
        warn(f"第{num:03d}章标题《{title}》过短，建议至少 {MIN_TITLE_LEN} 个字")
    if len(title) > MAX_TITLE_LEN:
        warn(f"第{num:03d}章标题《{title}》过长，建议不要超过 {MAX_TITLE_LEN} 个字")

    if title in title_repeats:
        warn(f"第{num:03d}章标题《{title}》与第{title_repeats[title]:03d}章重复")
    else:
        title_repeats[title] = num

# ================= 2. 伏笔引用与孤立检查 =================
print("  >>> 检查伏笔...")
foreshadow_file = CONTINUITY / "伏笔.yaml"
if foreshadow_file.exists():
    with open(foreshadow_file, encoding="utf-8") as f:
        fs_data = yaml.safe_load(f)

    def check_foreshadow(obj, path=""):
        if isinstance(obj, dict):
            if "status" in obj and "chapter" in obj:
                status = obj["status"]
                try:
                    ch = int(obj["chapter"])
                    if status == "active" and max_chapter - ch > FORESHADOW_ACTIVE_LIMIT:
                        warn(f"伏笔.yaml {path} 活跃超过{FORESHADOW_ACTIVE_LIMIT}章（第{ch:03d}章埋下），疑似被遗忘")
                except ValueError:
                    pass
            for k, v in obj.items():
                check_foreshadow(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                check_foreshadow(v, f"{path}[{i}]")
        elif isinstance(obj, str):
            for m in re.finditer(r"(?:第)?(\d{3})\s*(?:[-–~]\s*(\d{3}))?", obj):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else start
                for n in range(start, end + 1):
                    if n <= max_chapter and n not in chapters:
                        err(f"伏笔.yaml {path} 引用了不存在的第{n:03d}章")
    check_foreshadow(fs_data)

# ================= 3. 人物出场与关系检查 =================
print("  >>> 检查人物出场...")
char_file = CONTINUITY / "人物.yaml"
if char_file.exists() and chapters:
    with open(char_file, encoding="utf-8") as f:
        char_data = yaml.safe_load(f)

    character_names = set()
    def extract_names(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "characters" and isinstance(v, dict):
                    character_names.update(v.keys())
                if k == "name" and isinstance(v, str):
                    character_names.add(v)
                extract_names(v)
        elif isinstance(obj, list):
            for v in obj:
                extract_names(v)

    extract_names(char_data)

    for name in character_names:
        appear_in = [num for num, data in chapters.items() if name in data["content"]]
        if not appear_in:
            warn(f"人物.yaml 中的角色 '{name}' 在正文中未出现或拼写不一致")
        else:
            info(f"角色 '{name}' 出现在 第{min(appear_in):03d}章 至 第{max(appear_in):03d}章")

# ================= 4. 时间线逻辑检查 =================
print("  >>> 检查时间线...")
timeline_file = CONTINUITY / "时间线.yaml"
if timeline_file.exists():
    with open(timeline_file, encoding="utf-8") as f:
        tl_data = yaml.safe_load(f)
    def check_timeline(obj, path=""):
        if isinstance(obj, dict):
            if "start" in obj and "end" in obj:
                try:
                    if int(obj["start"]) > int(obj["end"]):
                        err(f"时间线.yaml {path} 的 start({obj['start']}) 大于 end({obj['end']})")
                except ValueError:
                    pass
            for k, v in obj.items():
                check_timeline(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                check_timeline(v, f"{path}[{i}]")
    check_timeline(tl_data)

# ================= 5. 合并 WSC 报告 =================
print("  >>> 合并 WSC 风格检查报告...")
wsc_report = ROOT / "log" / "wsc-report.json"
if wsc_report.exists():
    try:
        with open(wsc_report, encoding="utf-8") as f:
            wsc_data = json.load(f)
            if isinstance(wsc_data, dict) and "summary" in wsc_data:
                wsc_warnings = wsc_data["summary"].get("warnings", 0)
                if wsc_warnings > 20:
                    warn(f"WSC 风格检查发现 {wsc_warnings} 个问题，建议查看日志优化文本")
            elif isinstance(wsc_data, list):
                if len(wsc_data) > 20:
                    warn(f"WSC 风格检查发现 {len(wsc_data)} 个问题，建议查看日志优化文本")
    except Exception as e:
        warn(f"解析 WSC 报告失败: {e}")

# ================= 输出结果与日志 =================
print("\n" + "=" * 40)
if info_logs:
    print(f"ℹ️ 信息记录 ({len(info_logs)} 条，仅展示前5条):")
    for i in info_logs[:5]: print(f"   - {i}")

if errors:
    print(f"\n❌ 发现 {len(errors)} 个错误:")
    for e in errors: print(f"   - {e}")
else:
    print("\n✅ 未发现深度逻辑错误")

if warnings:
    print(f"\n⚠️ 发现 {len(warnings)} 个警告:")
    for w in warnings: print(f"   - {w}")

# 写入日志
log_dir = ROOT / "log"
log_dir.mkdir(exist_ok=True)

with open(log_dir / "深度检查.txt", "w", encoding="utf-8") as f:
    f.write(f"=== 错误 ({len(errors)}) ===\n")
    for e in errors: f.write(f"  - {e}\n")
    f.write(f"\n=== 警告 ({len(warnings)}) ===\n")
    for w in warnings: f.write(f"  - {w}\n")
    f.write(f"\n=== 信息 ({len(info_logs)}) ===\n")
    for i in info_logs: f.write(f"  - {i}\n")

with open(log_dir / "story_stats.txt", "w", encoding="utf-8") as f:
    total_words = sum(len(re.sub(r'\s', '', d["content"])) for d in chapters.values())
    f.write(f"《影笔代理人》统计报告\n")
    f.write(f"总章节数: {len(chapters)}\n")
    f.write(f"总字数(去除空白): {total_words}\n")

with open(log_dir / "story_validate.txt", "w", encoding="utf-8") as f:
    if errors:
        f.write(f"合规检查未通过，发现 {len(errors)} 个错误。\n")
    else:
        f.write("合规检查通过，未发现目录/引用错误。\n")
