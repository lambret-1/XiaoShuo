# 小说转漫剧全流程流水线

基于 [shuohao-skills](https://github.com/lambret-1/shuohao-skills) 的五阶段自动化流水线，将小说正文一键转换为完整的漫剧前置素材。

## 流水线阶段

```
小说正文
    │
    ▼
┌─────────────┐
│ 1. 改编大纲  │  novel-outline → outline.json / .md / report.html
│  (五件套)    │  改编说明 + 人物表 + 爽点表 + 分集梗概 + 资产清单
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 2. 角色设定  │  novel-characters → cast.json / .md / report.html
│  (角色卡)    │  人物画像 + 形象提示词 + 音色提示词 + 设定图版面
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 3. 美术资产  │  novel-art → art.json / .md / report.html
│  (场景+道具) │  场景一致性锚点 + 光照变体 + 叙事道具设定
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 4. 漫剧剧本  │  novel-script → script.json / .md / report.html
│  (场次+节拍) │  结构化节拍流 + 逐句台词 + 时长预算 + 爽点认领
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 5. 分镜表    │  novel-storyboard → storyboard.json / .md / report.html
│  (段→镜→图)  │  三层分镜 + H3视频提示词 + 生成批次单 + 配音对齐单
└─────────────┘
```

## 前置配置

### 1. 配置 GitHub Secrets

在仓库 `Settings → Secrets and variables → Actions` 中添加以下 Secrets：

| Secret 名称 | 必填 | 说明 |
|------------|------|------|
| `AI_API_KEY` | ✅ | AI 服务 API 密钥（OpenAI 兼容格式） |
| `AI_API_URL` | ❌ | AI 服务端点地址，默认 `https://api.openai.com/v1` |
| `AI_MODEL` | ❌ | 模型名称，默认 `gpt-4o` |

支持任何 OpenAI 兼容的 API 服务（如 DeepSeek、Moonshot、通义千问等），只需配置对应的 `AI_API_URL` 和 `AI_MODEL`。

### 2. 环境要求

- Node.js >= 18（流水线自动配置 Node 20）
- 零 npm 依赖，所有脚本仅使用 Node.js 标准库

## 使用方法

### 触发流水线

1. 进入仓库的 **Actions** 页面
2. 选择 **小说转漫剧全流程流水线**
3. 点击 **Run workflow**
4. 填写参数后点击运行

### 流水线参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `book_name` | 影笔代理人 | 作品名称，用于产物文件命名 |
| `source_dir` | 影笔代理人/正文 | 小说正文章节目录（相对于仓库根目录） |
| `output_dir` | 影笔代理人-剧本/流水线产物 | 产物输出目录 |
| `episodes` | 60 | 改编总集数 |
| `duration` | 3 | 单集时长（分钟） |
| `genre` | 都市悬疑 | 题材类型（决定爽点类型） |
| `adaptation` | 抽核 | 改编幅度：忠实 / 抽核 / 借壳 |
| `max_characters` | 30 | 角色设定上限数量 |
| `start_stage` | outline | 起始阶段，支持断点续跑 |

### 断点续跑

如果流水线在某个阶段失败，可以从失败的阶段重新开始：

- 将 `start_stage` 设置为失败的阶段（如 `characters`）
- 流水线会跳过已完成的阶段，从指定阶段继续
- 已生成的上游产物（如 outline.json）会被复用

**注意**：从中间阶段开始时，必须确保上游产物已存在于输出目录中。

## 产物说明

流水线完成后，输出目录包含以下文件：

### 核心数据文件

| 文件 | 说明 |
|------|------|
| `<书名>-outline.json` | 改编大纲完整数据（五件套） |
| `<书名>-cast.json` | 角色设定完整数据 |
| `<书名>-art.json` | 美术资产完整数据（场景+道具） |
| `<书名>-script.json` | 漫剧剧本完整数据（场次+节拍流） |
| `<书名>-storyboard.json` | 分镜表完整数据（段→分镜→分镜图） |

### 可读文档

| 文件 | 说明 |
|------|------|
| `<书名>-outline.md` | 大纲 Markdown 版 |
| `<书名>-cast.md` | 角色设定 Markdown 版 |
| `<书名>-art.md` | 美术设定 Markdown 版 |
| `<书名>-script.md` | 剧本 Markdown 版 |
| `<书名>-storyboard.md` | 分镜 Markdown 版（含 H3 提示词） |

### 交互报告

| 文件 | 说明 |
|------|------|
| `outline-report.html` | 大纲评审报告（KPI带/爽点时间轴/调度矩阵/质量门） |
| `cast-report.html` | 角色设定报告（角色卡/形象提示词/音色提示词） |
| `art-report.html` | 美术设定报告（场景卡/道具卡/锚点核对表） |
| `script-report.html` | 剧本报告（时长仪表/分集剧本/台词本） |
| `storyboard-report.html` | 分镜报告（节奏带/分镜表/生成批次单/配音对齐单） |

### 流水线元数据

| 文件 | 说明 |
|------|------|
| `pipeline-config.json` | 流水线配置和执行结果汇总 |
| `pipeline-status.json` | 各阶段执行状态 |
| `_work/` | 中间工作文件（分块、seed、批次结果） |

## 质量门

每个阶段都内置确定性质量门检查，由 shuohao-skills 的脚本执行：

| 阶段 | 质量门数量 | 核心检查项 |
|------|-----------|-----------|
| 大纲 | 14 道 | 角色分档上限、主场景上限、爽点间隔≤3集、每集钩子悬念、叙述体无对白 |
| 角色 | 多道 | 引文逐字、出图提示词不含人名、语言分工、非内置语言必须带ui |
| 美术 | 10 道 | 锚点3-5、无人无手、白底可抠、尺度短语、提示词英文 |
| 剧本 | 10 道 | 每集时长±15%、单句≤35字、钩子前3拍兑现、每场至少一个动作节拍、爽点认领 |
| 分镜 | 18 道 | 节拍全覆盖、单段≤15秒、每切2-5秒、H3对齐指令逐字对账、台词逐字进d块 |

质量门未通过时不会阻断流水线，会在日志中给出警告，产物照常输出供人工修复。

## 本地运行

也可以在本地直接运行流水线脚本：

```bash
# 克隆两个仓库
git clone https://github.com/lambret-1/XiaoShuo.git
git clone https://github.com/lambret-1/shuohao-skills.git

# 配置环境变量
export AI_API_KEY="your-api-key"
export AI_API_URL="https://api.openai.com/v1"  # 可选
export AI_MODEL="gpt-4o"  # 可选

# 运行全流程
cd XiaoShuo/.github/scripts
node pipeline-runner.mjs \
  --book "../../影笔代理人/正文" \
  --output "../../影笔代理人-剧本/流水线产物" \
  --skills "../../../shuohao-skills" \
  --name "影笔代理人" \
  --episodes 60 \
  --duration 3 \
  --genre "都市悬疑"
```

### 单阶段运行

每个阶段脚本也可以独立运行：

```bash
# 仅生成大纲
node pipeline-outline.mjs --book <小说文本> --output <输出目录> --skill <skill目录>

# 仅生成角色（需要上游 outline.json）
node pipeline-characters.mjs --outline <outline.json> --book <小说文本> --output <输出目录> --skill <skill目录>

# 仅生成美术
node pipeline-art.mjs --outline <outline.json> --output <输出目录> --skill <skill目录>

# 仅生成剧本
node pipeline-script.mjs --outline <outline.json> --output <输出目录> --skill <skill目录>

# 仅生成分镜
node pipeline-storyboard.mjs --script <script.json> --outline <outline.json> --output <输出目录> --skill <skill目录>
```

## 脚本架构

```
.github/scripts/
├── ai-client.mjs            # AI API 通用客户端（OpenAI兼容，自动重试，JSON提取）
├── pipeline-common.mjs      # 公共工具（文件操作、日志、命令执行、状态管理）
├── pipeline-runner.mjs      # 总控脚本（五阶段调度，断点续跑，产物汇总）
├── pipeline-outline.mjs     # 阶段1：改编大纲
├── pipeline-characters.mjs  # 阶段2：角色设定
├── pipeline-art.mjs         # 阶段3：美术资产
├── pipeline-script.mjs      # 阶段4：漫剧剧本
└── pipeline-storyboard.mjs  # 阶段5：分镜表
```

## 注意事项

1. **运行时间**：全流程（60集）可能需要数小时，取决于 AI 服务响应速度和集数
2. **API 费用**：流水线会大量调用 AI API，请注意 API 配额和费用
3. **内容质量**：AI 生成的内容需要人工审核和微调，质量门仅做结构性检查
4. **断点续跑**：建议分阶段运行，每阶段完成后检查产物质量再继续下一阶段
5. **长文本处理**：小说正文超过 6 万字时，大纲生成会自动截取前半部分用于骨架生成

## 故障排查

### AI_API_KEY 未配置

错误信息：`未配置 AI_API_KEY Secret，无法调用 AI 服务生成内容`

解决：在仓库 Settings → Secrets 中添加 `AI_API_KEY`。

### 质量门校验失败

质量门失败不会阻断流水线，会在日志中输出警告。可以：
1. 查看对应阶段的日志，了解具体失败项
2. 手动编辑生成的 JSON 文件修复问题
3. 重新运行该阶段的 `validate` 和 `render` 命令

### 某集生成失败

单个集/角色/场景生成失败时，流水线会写入占位内容并继续。可以在流水线完成后：
1. 查看 `pipeline-status.json` 了解哪些条目失败
2. 手动补充失败的内容
3. 重新运行校验和渲染

## 许可证

本流水线基于 shuohao-skills（Apache-2.0）构建。
