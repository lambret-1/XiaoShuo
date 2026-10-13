#!/usr/bin/env node
/**
 * 流水线阶段 1：改编大纲生成
 * 调用 novel-outline skill，从小说正文生成短剧改编大纲
 *
 * 输入：小说正文合并文本
 * 输出：outline.json / outline.md / outline-report.html
 */

import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { chatCompleteJson, chatComplete } from './ai-client.mjs';
import {
  ensureDir, readJson, writeJson, readText, writeText,
  logger, runCommand, truncate, writeStatus, fileExistsNonEmpty,
} from './pipeline-common.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * 构建大纲生成的系统提示词
 */
function buildOutlineSystemPrompt(schemaContent, outlinePassContent) {
  return `你是一位专业的短剧改编编剧，擅长将小说改编为高爽点短剧大纲。

## 工作规范
${outlinePassContent || '请按照专业短剧改编流程执行。'}

## 输出格式规范（严格遵守 JSON Schema）
${schemaContent || '输出必须为合法 JSON。'}

## 核心要求
1. 严格基于提供的小说原文内容，禁止凭空编造剧情
2. 每集必须有钩子（开场）和悬念（结尾）
3. 爽点分布均匀，间隔不超过 3 集
4. 角色分档清晰：主角组、重要配角、功能性角色
5. 主场景数量控制在合理范围
6. 关键取舍必须附原文证据（逐字片段）
7. 分集梗概为叙述体，禁止出现引号对白

只输出 JSON，不要输出任何解释性文字。`;
}

/**
 * 构建分集梗概生成的系统提示词
 */
function buildEpisodeSystemPrompt(episodePassContent) {
  return `你是一位专业的短剧分集编剧，负责将大纲骨架展开为详细的分集梗概。

## 分集写作规范
${episodePassContent || '每集包含：标题、开场钩子、核心剧情、爽点、结尾悬念。'}

## 核心要求
1. 严格遵循已拍板的大纲骨架，不擅自改线、改人、改爽点位置
2. 每集开场 3 拍内必须兑现钩子的具象画面
3. 每集结尾必须留下悬念
4. 梗概为叙述体，禁止出现引号对白
5. 标注该集用到的场景、出场角色、承载的爽点
6. 单集时长控制在目标范围内

只输出 JSON，不要输出任何解释性文字。`;
}

/**
 * 生成大纲骨架
 */
async function generateOutlineSkeleton({ bookText, bookName, episodes, duration, genre, adaptation, workDir, skillDir }) {
  logger.info('开始生成大纲骨架...');

  const schemaPath = path.join(skillDir, 'references', 'schema.md');
  const outlinePassPath = path.join(skillDir, 'references', 'outline-pass.md');
  const schemaContent = fileExistsNonEmpty(schemaPath) ? readText(schemaPath) : '';
  const outlinePassContent = fileExistsNonEmpty(outlinePassPath) ? readText(outlinePassPath) : '';

  // 截取小说前部分作为参考（避免超长）
  const maxInputChars = 60000;
  const bookExcerpt = bookText.length > maxInputChars
    ? bookText.slice(0, maxInputChars) + '\n\n...（原文过长，已截取前半部分用于骨架生成）'
    : bookText;

  const systemPrompt = buildOutlineSystemPrompt(schemaContent, outlinePassContent);
  const userPrompt = `## 小说名称
${bookName}

## 改编参数
- 总集数：${episodes} 集
- 单集时长：${duration} 分钟
- 题材：${genre}
- 改编幅度：${adaptation}

## 小说原文
${bookExcerpt}

## 任务
请生成短剧改编大纲骨架，包含以下四块：
1. adaptation（改编说明：改编幅度、关键取舍、保留/删减/合并的内容，每条取舍附原文证据）
2. characters（人物表：id、name、tier(lead/support/functional)、aliases、role、arc、from）
3. scenes（场景表：id、name、isPrimary、description、episodes）
4. beats（爽点表：id、episode、type、description、payoff）

输出为完整 JSON 对象。`;

  const skeleton = await chatCompleteJson([
    { role: 'system', content: systemPrompt },
    { role: 'user', content: userPrompt },
  ], { temperature: 0.7, maxTokens: 12000 });

  // 补充元数据
  skeleton.meta = {
    bookName,
    episodes: parseInt(episodes, 10),
    durationMinutes: parseInt(duration, 10),
    genre,
    adaptation,
    createdAt: new Date().toISOString(),
    lang: 'zh',
  };
  skeleton.episodes = [];

  const skeletonPath = path.join(workDir, 'outline-skeleton.json');
  writeJson(skeletonPath, skeleton);
  logger.success(`大纲骨架已生成：${skeletonPath}`);
  logger.info(`角色数：${skeleton.characters?.length || 0}，场景数：${skeleton.scenes?.length || 0}，爽点数：${skeleton.beats?.length || 0}`);

  return skeleton;
}

/**
 * 生成分集梗概（分批，每批最多 10 集）
 */
async function generateEpisodes({ skeleton, bookText, workDir, skillDir, episodes }) {
  logger.info(`开始生成分集梗概（共 ${episodes} 集，分批处理）...`);

  const episodePassPath = path.join(skillDir, 'references', 'episode-pass.md');
  const episodePassContent = fileExistsNonEmpty(episodePassPath) ? readText(episodePassPath) : '';
  const systemPrompt = buildEpisodeSystemPrompt(episodePassContent);

  const batchSize = 10;
  const allEpisodes = [];
  const totalBatches = Math.ceil(episodes / batchSize);

  for (let batch = 0; batch < totalBatches; batch++) {
    const startEp = batch * batchSize + 1;
    const endEp = Math.min(startEp + batchSize - 1, episodes);
    logger.step(batch + 1, totalBatches, `生成第 ${startEp}-${endEp} 集梗概...`);

    // 该批次的爽点
    const batchBeats = (skeleton.beats || []).filter(
      (b) => b.episode >= startEp && b.episode <= endEp
    );

    // 该批次可能用到的场景和角色
    const batchScenes = skeleton.scenes || [];
    const batchCharacters = skeleton.characters || [];

    const userPrompt = `## 已拍板的大纲骨架
### 改编说明
${JSON.stringify(skeleton.adaptation || {}, null, 2).slice(0, 3000)}

### 人物表
${JSON.stringify(batchCharacters.slice(0, 20), null, 2).slice(0, 4000)}

### 场景表
${JSON.stringify(batchScenes.slice(0, 15), null, 2).slice(0, 3000)}

### 本批次爽点
${JSON.stringify(batchBeats, null, 2)}

## 任务
请生成第 ${startEp} 集到第 ${endEp} 集的分集梗概。

每集格式：
{
  "ep": ${startEp},
  "title": "集标题",
  "hook": "开场钩子（具象画面描述）",
  "summary": "本集核心剧情叙述（200-400字）",
  "scenes": ["场景id列表"],
  "characters": ["出场角色id列表"],
  "beats": ["本集承载的爽点id列表"],
  "cliffhanger": "结尾悬念"
}

输出为 JSON 对象，包含 episodes 数组。`;

    try {
      const result = await chatCompleteJson([
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt },
      ], { temperature: 0.8, maxTokens: 16000 });

      const batchEps = result.episodes || result;
      if (Array.isArray(batchEps)) {
        allEpisodes.push(...batchEps);
        logger.info(`  本批生成 ${batchEps.length} 集`);
      } else {
        logger.warn(`  本批返回格式异常，跳过: ${truncate(JSON.stringify(result), 200)}`);
      }
    } catch (err) {
      logger.error(`  本批生成失败: ${err.message}`);
      // 生成占位集，避免后续校验完全失败
      for (let ep = startEp; ep <= endEp; ep++) {
        allEpisodes.push({
          ep,
          title: `第${ep}集（生成失败占位）`,
          hook: '待补充',
          summary: '本集生成失败，需人工补充。',
          scenes: [],
          characters: [],
          beats: [],
          cliffhanger: '待补充',
        });
      }
    }

    // 保存中间结果
    writeJson(path.join(workDir, `eps-${String(batch + 1).padStart(2, '0')}.json`), {
      batch: batch + 1,
      episodes: allEpisodes.filter((e) => e.ep >= startEp && e.ep <= endEp),
    });
  }

  // 按集数排序
  allEpisodes.sort((a, b) => (a.ep || 0) - (b.ep || 0));
  return allEpisodes;
}

/**
 * 校验大纲
 */
function validateOutline(outlinePath, skillDir) {
  const scriptPath = path.join(skillDir, 'scripts', 'novel-outline.mjs');
  if (!fileExistsNonEmpty(scriptPath)) {
    logger.warn('novel-outline.mjs 脚本不存在，跳过校验');
    return true;
  }

  logger.info('运行大纲质量门校验...');
  const result = runCommand(`node "${scriptPath}" validate "${outlinePath}"`, {
    timeout: 120000,
  });

  if (result.success) {
    logger.success('大纲质量门校验通过');
    return true;
  }

  logger.warn(`大纲质量门校验未通过（将继续输出，供人工修复）: ${truncate(result.error || result.stderr, 500)}`);
  return false;
}

/**
 * 渲染大纲输出
 */
function renderOutline(outlinePath, outputDir, bookName, skillDir) {
  const scriptPath = path.join(skillDir, 'scripts', 'novel-outline.mjs');
  if (!fileExistsNonEmpty(scriptPath)) {
    logger.warn('novel-outline.mjs 脚本不存在，跳过渲染');
    return;
  }

  logger.info('渲染大纲输出文件...');

  // Markdown
  const mdResult = runCommand(
    `node "${scriptPath}" render "${outlinePath}" --md --lang zh > "${path.join(outputDir, `${bookName}-outline.md`)}"`,
    { timeout: 120000 }
  );
  if (mdResult.success) {
    logger.success('Markdown 大纲已生成');
  } else {
    logger.warn(`Markdown 渲染失败: ${truncate(mdResult.error, 300)}`);
  }

  // HTML 报告
  const htmlResult = runCommand(
    `node "${scriptPath}" render "${outlinePath}" --html --lang zh > "${path.join(outputDir, 'outline-report.html')}"`,
    { timeout: 120000 }
  );
  if (htmlResult.success) {
    logger.success('HTML 大纲报告已生成');
  } else {
    logger.warn(`HTML 渲染失败: ${truncate(htmlResult.error, 300)}`);
  }
}

/**
 * 主入口
 */
export async function runOutlinePipeline(options) {
  const {
    bookText,
    bookName,
    episodes = 60,
    duration = 3,
    genre = '都市悬疑',
    adaptation = '抽核',
    outputDir,
    skillDir,
  } = options;

  logger.setPrefix('大纲');
  const workDir = path.join(outputDir, 'work-outline');
  ensureDir(workDir);
  ensureDir(outputDir);

  try {
    writeStatus(outputDir, 'outline', 'running', { startedAt: new Date().toISOString() });

    // Step 1: 生成大纲骨架
    const skeleton = await generateOutlineSkeleton({
      bookText, bookName, episodes, duration, genre, adaptation, workDir, skillDir,
    });

    // Step 2: 生成分集梗概
    const episodeList = await generateEpisodes({
      skeleton, bookText, workDir, skillDir, episodes: parseInt(episodes, 10),
    });

    // Step 3: 合并为完整 outline.json
    const fullOutline = { ...skeleton, episodes: episodeList };
    const outlinePath = path.join(outputDir, `${bookName}-outline.json`);
    writeJson(outlinePath, fullOutline);
    logger.success(`完整大纲已保存：${outlinePath}`);

    // Step 4: 校验
    const valid = validateOutline(outlinePath, skillDir);

    // Step 5: 渲染
    renderOutline(outlinePath, outputDir, bookName, skillDir);

    writeStatus(outputDir, 'outline', 'completed', {
      finishedAt: new Date().toISOString(),
      outlinePath,
      episodeCount: episodeList.length,
      characterCount: (skeleton.characters || []).length,
      sceneCount: (skeleton.scenes || []).length,
      beatCount: (skeleton.beats || []).length,
      validationPassed: valid,
    });

    return { outlinePath, success: true, validationPassed: valid };
  } catch (err) {
    logger.error(`大纲生成失败: ${err.message}`);
    writeStatus(outputDir, 'outline', 'failed', { error: err.message });
    throw err;
  }
}

// 命令行入口
if (import.meta.url === `file://${process.argv[1]}`) {
  const args = process.argv.slice(2);
  const opts = {};
  for (let i = 0; i < args.length; i += 2) {
    const key = args[i].replace(/^--/, '');
    opts[key] = args[i + 1];
  }

  if (!opts.book || !opts.output) {
    console.error('用法: node pipeline-outline.mjs --book <小说文本路径> --output <输出目录> --skill <skill目录> [--name 书名] [--episodes 集数] [--duration 时长] [--genre 题材]');
    process.exit(1);
  }

  const bookText = readText(opts.book);
  runOutlinePipeline({
    bookText,
    bookName: opts.name || '改编作品',
    episodes: opts.episodes || 60,
    duration: opts.duration || 3,
    genre: opts.genre || '都市悬疑',
    adaptation: opts.adaptation || '抽核',
    outputDir: opts.output,
    skillDir: opts.skill,
  }).then(() => {
    console.log('大纲流水线执行完成');
  }).catch((err) => {
    console.error('大纲流水线执行失败:', err);
    process.exit(1);
  });
}
