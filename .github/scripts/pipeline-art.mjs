#!/usr/bin/env node
/**
 * 流水线阶段 3：美术资产生成
 * 调用 novel-art skill，生成场景设定和叙事道具
 *
 * 输入：outline.json + cast.json
 * 输出：art.json / art.md / art-report.html
 */

import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chatCompleteJson } from './ai-client.mjs';
import {
  ensureDir, readJson, writeJson, readText,
  logger, runCommand, truncate, writeStatus, fileExistsNonEmpty, slugify,
} from './pipeline-common.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * 构建场景设定生成的系统提示词
 */
function buildSceneSystemPrompt(scenePassContent, schemaContent) {
  return `你是一位专业的美术设定师，擅长为 AI 短剧创建场景和道具设定集。

## 场景设定规范
${scenePassContent || '请按照专业场景设定流程执行。'}

## 输出格式规范
${schemaContent || '输出必须为合法 JSON。'}

## 核心要求
### 场景
1. 一致性锚点 3-5 个：必须是可画、可认、可核对的具体元素（如"补丁船篷"），不能是形容词（如"陈旧的氛围"）
2. 光照状态变体：从分集反推需要的时段，每个状态是完整的英文提示词
3. 空景出图提示词：**绝对不能出现人物**，全部英文
4. 能做变体就别开新景（variantOf 引用母场景）
5. 同批场景的空间气质必须有明显区分

### 叙事道具
1. 只收有特写、跨集出现、承载剧情的道具（通常 3-8 件）
2. 戏剧功能、锚点、状态变体
3. 尺度短语必须写进提示词（防止 AI 把手持道具画成家具）
4. 白底无手：设定图纯白背景，提示词中禁止出现手
5. 全部英文提示词，不含角色名

只输出 JSON，不要输出任何解释性文字。`;
}

/**
 * 使用 skill 脚本生成 seed 骨架
 */
function generateArtSeed(outlinePath, workDir, skillDir) {
  const scriptPath = path.join(skillDir, 'scripts', 'novel-art.mjs');
  if (!fileExistsNonEmpty(scriptPath)) {
    logger.warn('novel-art.mjs 脚本不存在，手动构建 seed');
    return null;
  }

  logger.info('从大纲生成美术 seed 骨架...');
  const seedPath = path.join(workDir, 'art-seed.json');
  const result = runCommand(`node "${scriptPath}" seed "${outlinePath}" > "${seedPath}"`, {
    timeout: 60000,
  });

  if (result.success && fileExistsNonEmpty(seedPath)) {
    const seed = readJson(seedPath);
    logger.success(`美术 seed 已生成，场景 ${seed.scenes?.length || 0} 个，道具 ${seed.props?.length || 0} 件`);
    return seed;
  }

  logger.warn(`美术 seed 生成失败: ${truncate(result.error || result.stderr, 300)}`);
  return null;
}

/**
 * 从大纲手动构建场景清单
 */
function buildSceneListFromOutline(outlinePath) {
  const outline = readJson(outlinePath);
  const scenes = outline.scenes || [];
  return scenes.map((s) => ({
    id: s.id,
    name: s.name,
    isPrimary: s.isPrimary || false,
    description: s.description || '',
    episodes: s.episodes || [],
    seedNote: '',
  }));
}

/**
 * 从大纲和剧本中提取叙事道具
 */
function extractPropsFromOutline(outlinePath) {
  const outline = readJson(outlinePath);
  // 大纲可能有 props 字段
  if (outline.props && Array.isArray(outline.props) && outline.props.length > 0) {
    return outline.props;
  }
  // 从分集梗概中提取常见叙事道具
  const props = [];
  const episodes = outline.episodes || [];
  const propKeywords = ['信', '日记', '照片', '钥匙', '手机', '文件', '盒子', '戒指', '项链', '枪', '药', '钱', '合同', '录音', 'U盘'];
  const found = new Set();
  for (const ep of episodes) {
    const summary = ep.summary || '';
    for (const kw of propKeywords) {
      if (summary.includes(kw) && !found.has(kw)) {
        found.add(kw);
        props.push({
          id: `prop-${slugify(kw)}`,
          name: kw,
          dramaFunction: `在剧情中承载关键信息或冲突`,
          episodes: [ep.ep],
          seedNote: '从分集梗概自动提取',
        });
      }
    }
  }
  return props.slice(0, 8);
}

/**
 * 为单个场景生成详细设定
 */
async function generateSceneDetail({ scene, allSceneNames, outlineExcerpt, workDir, skillDir }) {
  const scenePassPath = path.join(skillDir, 'references', 'scene-pass.md');
  const schemaPath = path.join(skillDir, 'references', 'schema.md');
  const scenePassContent = fileExistsNonEmpty(scenePassPath) ? readText(scenePassPath) : '';
  const schemaContent = fileExistsNonEmpty(schemaPath) ? readText(schemaPath) : '';

  const systemPrompt = buildSceneSystemPrompt(scenePassContent, schemaContent);

  const userPrompt = `## 场景基础信息
- 场景ID：${scene.id}
- 名称：${scene.name}
- 是否主场景：${scene.isPrimary ? '是' : '否'}
- 描述：${scene.description || '未提供'}
- 出现集数：${(scene.episodes || []).join(', ') || '未指定'}
- 备注：${scene.seedNote || '无'}

## 同批其他场景（避免气质撞车）
${allSceneNames.filter((n) => n !== scene.name).join('、')}

## 大纲参考
${outlineExcerpt}

## 任务
请为场景「${scene.name}」生成完整的美术设定，包含：
1. id（保持原样：${scene.id}）
2. name（保持原样：${scene.name}）
3. isPrimary（保持原样）
4. designIntent（设计意图，中文）
5. anchors（一致性锚点数组，3-5 个，中文，每个都是具体可画的元素）
6. lightingStates（光照状态数组，每个包含：name（中文）、prompt（英文完整提示词））
7. emptyScenePrompt（空景出图提示词，英文，绝对不能出现人物）
8. variantOf（如果是变体场景，填写母场景ID；否则为 null）
9. episodes（出现集数数组）

只输出该场景的 JSON 对象。`;

  const detail = await chatCompleteJson([
    { role: 'system', content: systemPrompt },
    { role: 'user', content: userPrompt },
  ], { temperature: 0.7, maxTokens: 8000 });

  detail.id = scene.id;
  detail.name = scene.name;

  return detail;
}

/**
 * 为单个道具生成详细设定
 */
async function generatePropDetail({ prop, workDir, skillDir }) {
  const propPassPath = path.join(skillDir, 'references', 'prop-pass.md');
  const propPassContent = fileExistsNonEmpty(propPassPath) ? readText(propPassPath) : '';

  const systemPrompt = `你是一位专业的道具设定师，为 AI 短剧创建叙事道具设定。

## 道具设定规范
${propPassContent || '请按照专业道具设定流程执行。'}

## 核心要求
1. 戏剧功能清晰
2. 锚点 2-4 个具体可识别元素
3. 状态变体至少 1 个（如合上/打开）
4. 尺度短语必须写进提示词（如"handheld size"、"palm-sized"）
5. 白底无手：设定图纯白背景，提示词禁止出现手和人物
6. 全部英文提示词

只输出 JSON。`;

  const userPrompt = `## 道具基础信息
- 道具ID：${prop.id}
- 名称：${prop.name}
- 戏剧功能：${prop.dramaFunction || '未指定'}
- 出现集数：${(prop.episodes || []).join(', ') || '未指定'}

## 任务
请为道具「${prop.name}」生成完整设定，包含：
1. id（保持原样）
2. name（保持原样）
3. dramaFunction（戏剧功能，中文）
4. anchors（锚点数组，2-4 个，中文）
5. scale（尺度描述，中文，如"手持大小"）
6. states（状态变体数组，每个包含：name（中文）、prompt（英文白底无手提示词，含尺度短语））
7. episodes（出现集数）

只输出该道具的 JSON 对象。`;

  const detail = await chatCompleteJson([
    { role: 'system', content: systemPrompt },
    { role: 'user', content: userPrompt },
  ], { temperature: 0.7, maxTokens: 6000 });

  detail.id = prop.id;
  detail.name = prop.name;
  return detail;
}

/**
 * 校验美术设定
 */
function validateArt(artPath, castPath, skillDir) {
  const scriptPath = path.join(skillDir, 'scripts', 'novel-art.mjs');
  if (!fileExistsNonEmpty(scriptPath)) {
    logger.warn('novel-art.mjs 脚本不存在，跳过校验');
    return true;
  }

  logger.info('运行美术设定质量门校验...');
  const castArg = castPath ? `--cast "${castPath}"` : '';
  const result = runCommand(`node "${scriptPath}" validate "${artPath}" ${castArg}`, {
    timeout: 120000,
  });

  if (result.success) {
    logger.success('美术设定质量门校验通过');
    return true;
  }

  logger.warn(`美术设定校验未通过（将继续输出）: ${truncate(result.error || result.stderr, 500)}`);
  return false;
}

/**
 * 渲染美术设定输出
 */
function renderArt(artPath, outputDir, bookName, skillDir) {
  const scriptPath = path.join(skillDir, 'scripts', 'novel-art.mjs');
  if (!fileExistsNonEmpty(scriptPath)) {
    logger.warn('novel-art.mjs 脚本不存在，跳过渲染');
    return;
  }

  logger.info('渲染美术设定输出...');

  const mdResult = runCommand(
    `node "${scriptPath}" render "${artPath}" --md --lang zh > "${path.join(outputDir, `${bookName}-art.md`)}"`,
    { timeout: 120000 }
  );
  if (mdResult.success) logger.success('美术设定 Markdown 已生成');

  const htmlResult = runCommand(
    `node "${scriptPath}" render "${artPath}" --html --lang zh > "${path.join(outputDir, 'art-report.html')}"`,
    { timeout: 120000 }
  );
  if (htmlResult.success) logger.success('美术设定 HTML 报告已生成');
}

/**
 * 主入口
 */
export async function runArtPipeline(options) {
  const {
    outlinePath,
    castPath = null,
    bookName,
    outputDir,
    skillDir,
    lang = 'zh',
  } = options;

  logger.setPrefix('美术');
  const workDir = path.join(outputDir, 'work-art');
  ensureDir(workDir);
  ensureDir(outputDir);

  try {
    writeStatus(outputDir, 'art', 'running', { startedAt: new Date().toISOString() });

    // Step 1: 生成或构建场景和道具清单
    let sceneList = [];
    let propList = [];
    const seed = generateArtSeed(outlinePath, workDir, skillDir);
    if (seed) {
      sceneList = seed.scenes || [];
      propList = seed.props || [];
    }
    if (sceneList.length === 0) {
      sceneList = buildSceneListFromOutline(outlinePath);
    }
    if (propList.length === 0) {
      propList = extractPropsFromOutline(outlinePath);
    }

    logger.info(`待生成场景数：${sceneList.length}，道具数：${propList.length}`);

    // Step 2: 准备大纲摘录
    const outline = readJson(outlinePath);
    const outlineExcerpt = JSON.stringify({
      adaptation: outline.adaptation,
      episodes: (outline.episodes || []).slice(0, 10).map((e) => ({
        ep: e.ep, title: e.title, summary: e.summary?.slice(0, 200), scenes: e.scenes,
      })),
    }, null, 2).slice(0, 20000);

    const allSceneNames = sceneList.map((s) => s.name);

    // Step 3: 逐个生成场景设定
    const scenes = [];
    for (let i = 0; i < sceneList.length; i++) {
      const scene = sceneList[i];
      logger.step(i + 1, sceneList.length, `生成场景「${scene.name}」设定...`);
      try {
        const detail = await generateSceneDetail({
          scene, allSceneNames, outlineExcerpt, workDir, skillDir,
        });
        scenes.push(detail);
      } catch (err) {
        logger.error(`  场景「${scene.name}」生成失败: ${err.message}`);
        scenes.push({
          id: scene.id, name: scene.name, isPrimary: scene.isPrimary,
          designIntent: '生成失败，待补充', anchors: [], lightingStates: [],
          emptyScenePrompt: '', variantOf: null, episodes: scene.episodes || [],
        });
      }
    }

    // Step 4: 逐个生成道具设定
    const props = [];
    for (let i = 0; i < propList.length; i++) {
      const prop = propList[i];
      logger.step(i + 1, propList.length, `生成道具「${prop.name}」设定...`);
      try {
        const detail = await generatePropDetail({ prop, workDir, skillDir });
        props.push(detail);
      } catch (err) {
        logger.error(`  道具「${prop.name}」生成失败: ${err.message}`);
        props.push({
          id: prop.id, name: prop.name, dramaFunction: '生成失败',
          anchors: [], scale: '', states: [], episodes: prop.episodes || [],
        });
      }
    }

    // Step 5: 合成 art.json
    const art = {
      meta: { source: bookName, lang, createdAt: new Date().toISOString() },
      scenes,
      props,
    };
    const artPath = path.join(outputDir, `${bookName}-art.json`);
    writeJson(artPath, art);
    logger.success(`美术设定已保存：${artPath}`);

    // Step 6: 校验
    const valid = validateArt(artPath, castPath, skillDir);

    // Step 7: 渲染
    renderArt(artPath, outputDir, bookName, skillDir);

    writeStatus(outputDir, 'art', 'completed', {
      finishedAt: new Date().toISOString(),
      artPath,
      sceneCount: scenes.length,
      propCount: props.length,
      validationPassed: valid,
    });

    return { artPath, success: true, validationPassed: valid };
  } catch (err) {
    logger.error(`美术设定生成失败: ${err.message}`);
    writeStatus(outputDir, 'art', 'failed', { error: err.message });
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
    console.error('用法: node pipeline-art.mjs --outline <outline.json> --output <输出目录> --skill <skill目录> [--cast <cast.json>] [--name 书名]');
    process.exit(1);
  }

  runArtPipeline({
    outlinePath: opts.outline,
    castPath: opts.cast || null,
    bookName: opts.name || '改编作品',
    outputDir: opts.output,
    skillDir: opts.skill,
  }).then(() => {
    console.log('美术设定流水线执行完成');
  }).catch((err) => {
    console.error('美术设定流水线执行失败:', err);
    process.exit(1);
  });
}
