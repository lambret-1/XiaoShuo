#!/usr/bin/env node
/**
 * 流水线阶段 5：分镜生成
 * 调用 novel-storyboard skill，从剧本生成分镜（段→分镜→分镜图）
 *
 * 输入：script.json + outline.json + cast.json + art.json
 * 输出：storyboard.json / storyboard.md / storyboard-report.html
 */

import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chatCompleteJson } from './ai-client.mjs';
import {
  ensureDir, readJson, writeJson, readText,
  logger, runCommand, truncate, writeStatus, fileExistsNonEmpty,
} from './pipeline-common.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * 构建分镜生成的系统提示词
 */
function buildStoryboardSystemPrompt(storyboardPassContent, schemaContent) {
  return `你是一位专业的分镜师，擅长为 AI 短剧创建详细的分镜表。

## 分镜创作规范
${storyboardPassContent || '请按照专业分镜创作流程执行。'}

## 输出格式规范
${schemaContent || '输出必须为合法 JSON。'}

## 核心要求
### 三层结构
1. **段（segment）**：一次视频生成，总时长 9-15 秒，不跨场次
2. **分镜（cut）**：段内 2-5 秒的剪切，认领剧本节拍
3. **分镜图（frame）**：每切一张关键帧的画面提示词

### 镜头认领节拍
- 每个镜头声明覆盖剧本某场的哪几个连续节拍（sceneIndex + beats:[起,止]）
- 镜头不许跨场次——换景必换镜
- 每个节拍被恰好一个镜头认领、顺序不乱

### 分镜图提示词（frame）
- 中文，直呼角色名
- 必须包含中文景别词（特写/近景/中景/全景/远景）
- 描述画面构图、角色位置、表情动作、环境

### 镜头正文（shot）
- 中文，通用身份（不直呼角色名，用"男子""女子"等）
- 写这几秒发生什么
- 不写时间、镜头编号、图片引用

### 构图量化字段（每镜必填）
- focalLength: 焦距（特写/近景/中景/全景/远景）
- cameraAngle: 机位（平视/仰视/俯视/过肩）
- composition: 构图（居中/三分法/对称/框架）
- eyeLine: 视线落点
- focus: 焦点
- stability: 稳定性（固定/缓推/缓拉/摇/跟）

### 每段必填
- blocking: 谁在左谁在右、间距
- soundscape: 声景描述
- h3Prompt: MiniMax H3 视频提示词（英文，逐镜换行，含对齐指令和切点时刻）

### 约束
- 单段总时长 9-15 秒
- 每切 2-5 秒
- 同框不超过 3 人（超了必须带拆解说明）
- 台词装得进分镜：认领节拍的台词秒数 ≤ 镜头秒数
- 视频提示词不含角色名

只输出 JSON，不要输出任何解释性文字。`;
}

/**
 * 使用 skill 脚本生成 seed 工作底稿
 */
function generateStoryboardSeed(scriptPath, workDir, skillDir, epsRange) {
  const scriptToolPath = path.join(skillDir, 'scripts', 'novel-storyboard.mjs');
  if (!fileExistsNonEmpty(scriptToolPath)) {
    logger.warn('novel-storyboard.mjs 脚本不存在，手动构建 seed');
    return null;
  }

  logger.info(`从剧本生成分镜 seed 底稿（第 ${epsRange} 集）...`);
  const seedPath = path.join(workDir, `storyboard-seed-${epsRange.replace('-', '_')}.json`);
  const result = runCommand(
    `node "${scriptToolPath}" seed "${scriptPath}" --eps ${epsRange} > "${seedPath}"`,
    { timeout: 60000 }
  );

  if (result.success && fileExistsNonEmpty(seedPath)) {
    const seed = readJson(seedPath);
    logger.success('分镜 seed 底稿已生成');
    return seed;
  }

  logger.warn(`分镜 seed 生成失败: ${truncate(result.error || result.stderr, 300)}`);
  return null;
}

/**
 * 为单集生成分镜
 */
async function generateEpisodeStoryboard({
  episodeScript, outline, art, cast, workDir, skillDir,
}) {
  const storyboardPassPath = path.join(skillDir, 'references', 'storyboard-pass.md');
  const schemaPath = path.join(skillDir, 'references', 'schema.md');
  const storyboardPassContent = fileExistsNonEmpty(storyboardPassPath) ? readText(storyboardPassPath) : '';
  const schemaContent = fileExistsNonEmpty(schemaPath) ? readText(schemaPath) : '';

  const systemPrompt = buildStoryboardSystemPrompt(storyboardPassContent, schemaContent);

  // 准备场景信息
  const sceneIds = (episodeScript.scenes || []).map((s) => s.sceneId);
  const relevantScenes = (art.scenes || [])
    .filter((s) => sceneIds.includes(s.id) || sceneIds.includes(s.name))
    .map((s) => ({ id: s.id, name: s.name, anchors: s.anchors, emptyScenePrompt: s.emptyScenePrompt }));

  // 准备角色信息
  const allSpeakers = new Set();
  for (const sc of episodeScript.scenes || []) {
    for (const beat of sc.beats || []) {
      if (beat.type === 'dialogue' && beat.speaker) {
        allSpeakers.add(beat.speaker);
      }
    }
  }
  const relevantChars = (cast.characters || [])
    .filter((c) => allSpeakers.has(c.name) || allSpeakers.has(c.id))
    .map((c) => ({ id: c.id, name: c.name, appearance: c.image?.appearance, vibe: c.image?.vibe }));

  // 序列化剧本节拍供参考
  const beatsReference = (episodeScript.scenes || []).map((sc, si) => ({
    sceneIndex: si,
    sceneId: sc.sceneId,
    lighting: sc.lighting,
    beats: (sc.beats || []).map((b, bi) => ({
      beatIndex: bi,
      type: b.type,
      text: b.type === 'action' ? b.text : undefined,
      speaker: b.type === 'dialogue' ? b.speaker : undefined,
      dialogue: b.type === 'dialogue' ? b.text : undefined,
      delivery: b.type === 'dialogue' ? b.delivery : undefined,
    })),
  }));

  const targetSeconds = episodeScript.targetSeconds || 180;

  const userPrompt = `## 第 ${episodeScript.ep} 集分镜任务
- 集标题：${episodeScript.title}
- 目标总时长：${targetSeconds} 秒
- 开场钩子位置：第 ${episodeScript.hookBeat || 0} 拍

## 剧本节拍（必须全部认领，顺序不乱）
${JSON.stringify(beatsReference, null, 2)}

## 可用场景设定
${JSON.stringify(relevantScenes, null, 2)}

## 出场角色形象
${JSON.stringify(relevantChars, null, 2)}

## 任务
请为第 ${episodeScript.ep} 集生成完整分镜，结构如下：
{
  "ep": ${episodeScript.ep},
  "title": "${episodeScript.title}",
  "segments": [
    {
      "segmentId": "E${String(episodeScript.ep).padStart(2, '0')}-01",
      "totalSeconds": 12,
      "blocking": "角色位置描述",
      "soundscape": "声景描述",
      "music": "配乐描述（可选）",
      "h3Prompt": "完整的 MiniMax H3 视频提示词（英文，逐镜换行）",
      "cuts": [
        {
          "cutIndex": 0,
          "seconds": 4,
          "sceneIndex": 0,
          "beats": [0, 1],
          "frame": "分镜图提示词（中文，含景别词，直呼角色名）",
          "shot": "镜头正文（中文，通用身份）",
          "focalLength": "近景",
          "cameraAngle": "平视",
          "composition": "三分法",
          "eyeLine": "视线落点",
          "focus": "焦点",
          "stability": "固定"
        }
      ]
    }
  ]
}

要求：
- 所有剧本节拍必须被恰好一个镜头认领，顺序连续
- 每段 9-15 秒，每切 2-5 秒
- 镜头不跨场次
- 第一段第一镜必须呈现开场钩子
- 最后一段最后一镜必须呈现结尾悬念

只输出该集的 JSON 对象。`;

  const storyboard = await chatCompleteJson([
    { role: 'system', content: systemPrompt },
    { role: 'user', content: userPrompt },
  ], { temperature: 0.7, maxTokens: 16000 });

  storyboard.ep = episodeScript.ep;
  return storyboard;
}

/**
 * 校验分镜
 */
function validateStoryboard(storyboardPath, scriptPath, outlinePath, castPath, artPath, skillDir) {
  const scriptToolPath = path.join(skillDir, 'scripts', 'novel-storyboard.mjs');
  if (!fileExistsNonEmpty(scriptToolPath)) {
    logger.warn('novel-storyboard.mjs 脚本不存在，跳过校验');
    return true;
  }

  logger.info('运行分镜质量门校验...');
  const castArg = castPath ? `--cast "${castPath}"` : '';
  const artArg = artPath ? `--art "${artPath}"` : '';
  const result = runCommand(
    `node "${scriptToolPath}" validate "${storyboardPath}" --script "${scriptPath}" --outline "${outlinePath}" ${castArg} ${artArg}`,
    { timeout: 120000 }
  );

  if (result.success) {
    logger.success('分镜质量门校验通过');
    return true;
  }

  logger.warn(`分镜校验未通过（将继续输出）: ${truncate(result.error || result.stderr, 500)}`);
  return false;
}

/**
 * 渲染分镜输出
 */
function renderStoryboard(storyboardPath, scriptPath, outlinePath, artPath, outputDir, bookName, skillDir) {
  const scriptToolPath = path.join(skillDir, 'scripts', 'novel-storyboard.mjs');
  if (!fileExistsNonEmpty(scriptToolPath)) {
    logger.warn('novel-storyboard.mjs 脚本不存在，跳过渲染');
    return;
  }

  logger.info('渲染分镜输出...');
  const artArg = artPath ? `--art "${artPath}"` : '';

  const mdResult = runCommand(
    `node "${scriptToolPath}" render "${storyboardPath}" --md --script "${scriptPath}" --outline "${outlinePath}" ${artArg} --lang zh > "${path.join(outputDir, `${bookName}-storyboard.md`)}"`,
    { timeout: 120000 }
  );
  if (mdResult.success) logger.success('分镜 Markdown 已生成');

  const htmlResult = runCommand(
    `node "${scriptToolPath}" render "${storyboardPath}" --html --script "${scriptPath}" --outline "${outlinePath}" ${artArg} --lang zh > "${path.join(outputDir, 'storyboard-report.html')}"`,
    { timeout: 120000 }
  );
  if (htmlResult.success) logger.success('分镜 HTML 报告已生成');
}

/**
 * 主入口
 */
export async function runStoryboardPipeline(options) {
  const {
    scriptPath,
    outlinePath,
    artPath = null,
    castPath = null,
    bookName,
    outputDir,
    skillDir,
    lang = 'zh',
    batchSize = 3,
    startEp = 1,
    endEp = null,
  } = options;

  logger.setPrefix('分镜');
  const workDir = path.join(outputDir, 'work-storyboard');
  ensureDir(workDir);
  ensureDir(outputDir);

  try {
    writeStatus(outputDir, 'storyboard', 'running', { startedAt: new Date().toISOString() });

    const script = readJson(scriptPath);
    const outline = readJson(outlinePath);
    const art = artPath ? readJson(artPath) : { scenes: [] };
    const cast = castPath ? readJson(castPath) : { characters: [] };

    const totalEpisodes = endEp || script.episodes?.length || 60;
    const episodes = (script.episodes || [])
      .filter((e) => e.ep >= startEp && e.ep <= totalEpisodes)
      .sort((a, b) => a.ep - b.ep);

    logger.info(`待生成分镜集数：${episodes.length}（第 ${startEp}-${totalEp} 集）`);

    // 分批生成
    const allEpisodeStoryboards = [];
    const totalBatches = Math.ceil(episodes.length / batchSize);

    for (let batch = 0; batch < totalBatches; batch++) {
      const batchEps = episodes.slice(batch * batchSize, (batch + 1) * batchSize);
      const batchStart = batchEps[0].ep;
      const batchEnd = batchEps[batchEps.length - 1].ep;
      logger.step(batch + 1, totalBatches, `生成第 ${batchStart}-${batchEnd} 集分镜...`);

      // 生成 seed
      const epsRange = `${batchStart}-${batchEnd}`;
      generateStoryboardSeed(scriptPath, workDir, skillDir, epsRange);

      // 逐集生成
      for (const epScript of batchEps) {
        logger.info(`  第 ${epScript.ep} 集：${epScript.title}`);
        try {
          const epStoryboard = await generateEpisodeStoryboard({
            episodeScript: epScript, outline, art, cast, workDir, skillDir,
          });
          allEpisodeStoryboards.push(epStoryboard);
        } catch (err) {
          logger.error(`  第 ${epScript.ep} 集分镜生成失败: ${err.message}`);
          allEpisodeStoryboards.push({
            ep: epScript.ep, title: epScript.title, segments: [],
            error: '生成失败，需人工补充',
          });
        }
      }

      // 保存中间结果
      writeJson(path.join(workDir, `storyboard-batch-${String(batch + 1).padStart(2, '0')}.json`), {
        batch: batch + 1,
        episodes: allEpisodeStoryboards.filter((e) => e.ep >= batchStart && e.ep <= batchEnd),
      });
    }

    // 统计
    let totalSegments = 0;
    let totalCuts = 0;
    for (const ep of allEpisodeStoryboards) {
      for (const seg of ep.segments || []) {
        totalSegments++;
        totalCuts += (seg.cuts || []).length;
      }
    }

    // 合成完整 storyboard.json
    const fullStoryboard = {
      meta: {
        source: bookName, lang, createdAt: new Date().toISOString(),
        episodes: allEpisodeStoryboards.length,
        totalSegments,
        totalCuts,
      },
      episodes: allEpisodeStoryboards,
    };
    const storyboardPath = path.join(outputDir, `${bookName}-storyboard.json`);
    writeJson(storyboardPath, fullStoryboard);
    logger.success(`完整分镜已保存：${storyboardPath}（${totalSegments} 段，${totalCuts} 镜）`);

    // 校验
    const valid = validateStoryboard(storyboardPath, scriptPath, outlinePath, castPath, artPath, skillDir);

    // 渲染
    renderStoryboard(storyboardPath, scriptPath, outlinePath, artPath, outputDir, bookName, skillDir);

    writeStatus(outputDir, 'storyboard', 'completed', {
      finishedAt: new Date().toISOString(),
      storyboardPath,
      episodeCount: allEpisodeStoryboards.length,
      totalSegments,
      totalCuts,
      validationPassed: valid,
    });

    return { storyboardPath, success: true, validationPassed: valid };
  } catch (err) {
    logger.error(`分镜生成失败: ${err.message}`);
    writeStatus(outputDir, 'storyboard', 'failed', { error: err.message });
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

  if (!opts.script || !opts.outline || !opts.output || !opts.skill) {
    console.error('用法: node pipeline-storyboard.mjs --script <script.json> --outline <outline.json> --output <输出目录> --skill <skill目录> [--art <art.json>] [--cast <cast.json>] [--name 书名] [--start 起始集] [--end 结束集]');
    process.exit(1);
  }

  runStoryboardPipeline({
    scriptPath: opts.script,
    outlinePath: opts.outline,
    artPath: opts.art || null,
    castPath: opts.cast || null,
    bookName: opts.name || '改编作品',
    outputDir: opts.output,
    skillDir: opts.skill,
    startEp: parseInt(opts.start || '1', 10),
    endEp: opts.end ? parseInt(opts.end, 10) : null,
  }).then(() => {
    console.log('分镜流水线执行完成');
  }).catch((err) => {
    console.error('分镜流水线执行失败:', err);
    process.exit(1);
  });
}
