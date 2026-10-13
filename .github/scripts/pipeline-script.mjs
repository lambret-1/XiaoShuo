#!/usr/bin/env node
/**
 * 流水线阶段 4：漫剧剧本生成
 * 调用 novel-script skill，从大纲生成结构化剧本（场次+节拍流）
 *
 * 输入：outline.json + art.json + cast.json
 * 输出：script.json / script.md / script-report.html
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
 * 构建剧本生成的系统提示词
 */
function buildScriptSystemPrompt(scriptPassContent, schemaContent) {
  return `你是一位专业的短剧编剧，擅长将分集梗概展开为结构化的剧本。

## 剧本写作规范
${scriptPassContent || '请按照专业剧本写作流程执行。'}

## 输出格式规范
${schemaContent || '输出必须为合法 JSON。'}

## 核心要求
1. **剧本管戏，分镜管拍**：只有集、场次、节拍流，没有镜号
2. **节拍流结构**：动作节拍（action）与台词行（dialogue）交替
3. **台词必须结构化**：每句台词独立条目，包含 speaker（说话人）、text（台词）、delivery（语气）
4. **动作节拍只写常见动作**：AI 能稳定生成的动作（走路、坐下、开门、拿东西），不写精巧动作
5. **每集第 1 拍冷开场兑现钩子**：hookBeat 认领，必须在全集前 3 拍内
6. **每集结尾一拍必须是悬念**
7. **每场至少一个动作节拍**：纯对白场是广播剧
8. **单句台词 ≤ 35 字**：口语化、一口气说完
9. **时长预算**：台词按 4.5 字/秒、动作按 2.5 秒/拍估算，控制在目标 ±15%
10. **爽点认领**：大纲说这集有大爆点，剧本必须有戏认领
11. **动作叙述体不混引号对白**
12. **谁的话像谁**：结合角色性格和说话方式

只输出 JSON，不要输出任何解释性文字。`;
}

/**
 * 使用 skill 脚本生成 seed 骨架
 */
function generateScriptSeed(outlinePath, workDir, skillDir, epsRange) {
  const scriptPath = path.join(skillDir, 'scripts', 'novel-script.mjs');
  if (!fileExistsNonEmpty(scriptPath)) {
    logger.warn('novel-script.mjs 脚本不存在，手动构建 seed');
    return null;
  }

  logger.info(`从大纲生成剧本 seed 骨架（第 ${epsRange} 集）...`);
  const seedPath = path.join(workDir, `script-seed-${epsRange.replace('-', '_')}.json`);
  const result = runCommand(
    `node "${scriptPath}" seed "${outlinePath}" --eps ${epsRange} > "${seedPath}"`,
    { timeout: 60000 }
  );

  if (result.success && fileExistsNonEmpty(seedPath)) {
    const seed = readJson(seedPath);
    logger.success(`剧本 seed 已生成`);
    return seed;
  }

  logger.warn(`剧本 seed 生成失败: ${truncate(result.error || result.stderr, 300)}`);
  return null;
}

/**
 * 为单集生成详细剧本
 */
async function generateEpisodeScript({
  episode, outline, art, cast, prevEpisode, workDir, skillDir,
}) {
  const scriptPassPath = path.join(skillDir, 'references', 'script-pass.md');
  const schemaPath = path.join(skillDir, 'references', 'schema.md');
  const scriptPassContent = fileExistsNonEmpty(scriptPassPath) ? readText(scriptPassPath) : '';
  const schemaContent = fileExistsNonEmpty(schemaPath) ? readText(schemaPath) : '';

  const systemPrompt = buildScriptSystemPrompt(scriptPassContent, schemaContent);

  // 准备该集用到的场景信息
  const sceneIds = episode.scenes || [];
  const relevantScenes = (art.scenes || [])
    .filter((s) => sceneIds.includes(s.id) || sceneIds.includes(s.name))
    .map((s) => ({ id: s.id, name: s.name, anchors: s.anchors, lightingStates: (s.lightingStates || []).map((l) => l.name) }));

  // 准备该集出场角色信息
  const charIds = episode.characters || [];
  const relevantChars = (cast.characters || [])
    .filter((c) => charIds.includes(c.id) || charIds.includes(c.name))
    .map((c) => ({
      id: c.id, name: c.name, aliases: c.aliases,
      personality: c.persona?.personality, speakingStyle: c.persona?.speakingStyle,
    }));

  // 该集爽点
  const episodeBeats = (outline.beats || []).filter((b) => b.episode === episode.ep);

  const targetSeconds = (outline.meta?.durationMinutes || 3) * 60;

  const userPrompt = `## 第 ${episode.ep} 集基础信息
- 集标题：${episode.title}
- 开场钩子：${episode.hook}
- 本集梗概：${episode.summary}
- 结尾悬念：${episode.cliffhanger}
- 目标时长：${targetSeconds} 秒（±15%）
- 本集爽点：${JSON.stringify(episodeBeats)}

${prevEpisode ? `## 上一集结尾悬念（开场要接上）\n${prevEpisode.cliffhanger}` : ''}

## 本集可用场景
${JSON.stringify(relevantScenes, null, 2)}

## 本集出场角色
${JSON.stringify(relevantChars, null, 2)}

## 任务
请生成第 ${episode.ep} 集的完整剧本，结构如下：
{
  "ep": ${episode.ep},
  "title": "${episode.title}",
  "hookBeat": 0,
  "targetSeconds": ${targetSeconds},
  "scenes": [
    {
      "sceneIndex": 0,
      "sceneId": "场景ID",
      "lighting": "光照状态名",
      "beats": [
        { "type": "action", "text": "动作描述（叙述体，无引号）" },
        { "type": "dialogue", "speaker": "角色名或ID", "text": "台词内容", "delivery": "语气描述" }
      ]
    }
  ]
}

要求：
- 第 1 拍（beats[0]）必须是动作节拍，兑现开场钩子的具象画面
- 最后一拍必须是动作节拍，呈现结尾悬念
- 每场至少一个动作节拍
- 单句台词不超过 35 字
- 动作只写 AI 能稳定生成的常见动作
- 估算总时长接近目标秒数

只输出该集的 JSON 对象。`;

  const script = await chatCompleteJson([
    { role: 'system', content: systemPrompt },
    { role: 'user', content: userPrompt },
  ], { temperature: 0.8, maxTokens: 12000 });

  script.ep = episode.ep;
  return script;
}

/**
 * 校验剧本
 */
function validateScript(scriptPath, outlinePath, artPath, skillDir) {
  const scriptPathTool = path.join(skillDir, 'scripts', 'novel-script.mjs');
  if (!fileExistsNonEmpty(scriptPathTool)) {
    logger.warn('novel-script.mjs 脚本不存在，跳过校验');
    return true;
  }

  logger.info('运行剧本质量门校验...');
  const artArg = artPath ? `--art "${artPath}"` : '';
  const result = runCommand(
    `node "${scriptPathTool}" validate "${scriptPath}" --outline "${outlinePath}" ${artArg}`,
    { timeout: 120000 }
  );

  if (result.success) {
    logger.success('剧本质量门校验通过');
    return true;
  }

  logger.warn(`剧本校验未通过（将继续输出）: ${truncate(result.error || result.stderr, 500)}`);
  return false;
}

/**
 * 渲染剧本输出
 */
function renderScript(scriptPath, outlinePath, artPath, castPath, outputDir, bookName, skillDir) {
  const scriptPathTool = path.join(skillDir, 'scripts', 'novel-script.mjs');
  if (!fileExistsNonEmpty(scriptPathTool)) {
    logger.warn('novel-script.mjs 脚本不存在，跳过渲染');
    return;
  }

  logger.info('渲染剧本输出...');
  const artArg = artPath ? `--art "${artPath}"` : '';
  const castArg = castPath ? `--cast "${castPath}"` : '';

  const mdResult = runCommand(
    `node "${scriptPathTool}" render "${scriptPath}" --md --outline "${outlinePath}" ${artArg} --lang zh > "${path.join(outputDir, `${bookName}-script.md`)}"`,
    { timeout: 120000 }
  );
  if (mdResult.success) logger.success('剧本 Markdown 已生成');

  const htmlResult = runCommand(
    `node "${scriptPathTool}" render "${scriptPath}" --html --outline "${outlinePath}" ${artArg} ${castArg} --lang zh > "${path.join(outputDir, 'script-report.html')}"`,
    { timeout: 120000 }
  );
  if (htmlResult.success) logger.success('剧本 HTML 报告已生成');
}

/**
 * 主入口
 */
export async function runScriptPipeline(options) {
  const {
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

  logger.setPrefix('剧本');
  const workDir = path.join(outputDir, 'work-script');
  ensureDir(workDir);
  ensureDir(outputDir);

  try {
    writeStatus(outputDir, 'script', 'running', { startedAt: new Date().toISOString() });

    const outline = readJson(outlinePath);
    const art = artPath ? readJson(artPath) : { scenes: [], props: [] };
    const cast = castPath ? readJson(castPath) : { characters: [] };

    const totalEpisodes = endEp || outline.episodes?.length || (outline.meta?.episodes || 60);
    const episodes = (outline.episodes || [])
      .filter((e) => e.ep >= startEp && e.ep <= totalEpisodes)
      .sort((a, b) => a.ep - b.ep);

    logger.info(`待生成剧本集数：${episodes.length}（第 ${startEp}-${totalEp} 集）`);

    // 分批生成
    const allEpisodeScripts = [];
    const totalBatches = Math.ceil(episodes.length / batchSize);

    for (let batch = 0; batch < totalBatches; batch++) {
      const batchEps = episodes.slice(batch * batchSize, (batch + 1) * batchSize);
      const batchStart = batchEps[0].ep;
      const batchEnd = batchEps[batchEps.length - 1].ep;
      logger.step(batch + 1, totalBatches, `生成第 ${batchStart}-${batchEnd} 集剧本...`);

      // 生成 seed
      const epsRange = `${batchStart}-${batchEnd}`;
      generateScriptSeed(outlinePath, workDir, skillDir, epsRange);

      // 逐集生成
      for (let i = 0; i < batchEps.length; i++) {
        const ep = batchEps[i];
        const prevEp = batch > 0 || i > 0
          ? allEpisodeScripts[allEpisodeScripts.length - 1]
          : null;

        logger.info(`  第 ${ep.ep} 集：${ep.title}`);
        try {
          const epScript = await generateEpisodeScript({
            episode: ep, outline, art, cast, prevEpisode: prevEp, workDir, skillDir,
          });
          allEpisodeScripts.push(epScript);
        } catch (err) {
          logger.error(`  第 ${ep.ep} 集生成失败: ${err.message}`);
          allEpisodeScripts.push({
            ep: ep.ep, title: ep.title, hookBeat: 0,
            targetSeconds: (outline.meta?.durationMinutes || 3) * 60,
            scenes: [{
              sceneIndex: 0, sceneId: 'unknown', lighting: '未知',
              beats: [
                { type: 'action', text: `第${ep.ep}集生成失败，需人工补充。梗概：${ep.summary?.slice(0, 100)}` },
              ],
            }],
          });
        }
      }

      // 保存中间结果
      writeJson(path.join(workDir, `script-batch-${String(batch + 1).padStart(2, '0')}.json`), {
        batch: batch + 1,
        episodes: allEpisodeScripts.filter((e) => e.ep >= batchStart && e.ep <= batchEnd),
      });
    }

    // 合成完整 script.json
    const fullScript = {
      meta: {
        source: bookName, lang, createdAt: new Date().toISOString(),
        episodes: allEpisodeScripts.length,
        targetDurationMinutes: outline.meta?.durationMinutes || 3,
      },
      episodes: allEpisodeScripts,
    };
    const scriptPath = path.join(outputDir, `${bookName}-script.json`);
    writeJson(scriptPath, fullScript);
    logger.success(`完整剧本已保存：${scriptPath}`);

    // 校验
    const valid = validateScript(scriptPath, outlinePath, artPath, skillDir);

    // 渲染
    renderScript(scriptPath, outlinePath, artPath, castPath, outputDir, bookName, skillDir);

    writeStatus(outputDir, 'script', 'completed', {
      finishedAt: new Date().toISOString(),
      scriptPath,
      episodeCount: allEpisodeScripts.length,
      validationPassed: valid,
    });

    return { scriptPath, success: true, validationPassed: valid };
  } catch (err) {
    logger.error(`剧本生成失败: ${err.message}`);
    writeStatus(outputDir, 'script', 'failed', { error: err.message });
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

  if (!opts.outline || !opts.output || !opts.skill) {
    console.error('用法: node pipeline-script.mjs --outline <outline.json> --output <输出目录> --skill <skill目录> [--art <art.json>] [--cast <cast.json>] [--name 书名] [--start 起始集] [--end 结束集]');
    process.exit(1);
  }

  runScriptPipeline({
    outlinePath: opts.outline,
    artPath: opts.art || null,
    castPath: opts.cast || null,
    bookName: opts.name || '改编作品',
    outputDir: opts.output,
    skillDir: opts.skill,
    startEp: parseInt(opts.start || '1', 10),
    endEp: opts.end ? parseInt(opts.end, 10) : null,
  }).then(() => {
    console.log('剧本流水线执行完成');
  }).catch((err) => {
    console.error('剧本流水线执行失败:', err);
    process.exit(1);
  });
}
