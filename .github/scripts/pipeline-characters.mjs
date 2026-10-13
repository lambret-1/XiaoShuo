#!/usr/bin/env node
/**
 * 流水线阶段 2：角色设定生成
 * 调用 novel-characters skill，从大纲和小说正文生成角色设定
 *
 * 输入：outline.json + 小说正文
 * 输出：cast.json / cast.md / report.html
 */

import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chatCompleteJson } from './ai-client.mjs';
import {
  ensureDir, readJson, writeJson, readText, writeText,
  logger, runCommand, truncate, writeStatus, fileExistsNonEmpty, slugify,
} from './pipeline-common.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * 构建角色卡生成的系统提示词
 */
function buildCharacterSystemPrompt(profilePassContent, schemaContent) {
  return `你是一位专业的角色设定师，擅长为短剧创建详细的角色设定卡。

## 角色设定规范
${profilePassContent || '请按照专业角色设定流程执行。'}

## 输出格式规范
${schemaContent || '输出必须为合法 JSON。'}

## 核心要求
1. 人物档案：身份背景、性格特征、人物弧光、说话方式
2. 形象提示词：永远使用英文，包含外貌、服装、气质、设定图版面指令
3. 形象提示词中**绝对不能出现角色名字**
4. 音色提示词：永远使用英文，描述声线、语速、语气特点
5. 同批角色的长相和声线必须有明显区分，避免撞车
6. 所有设计必须基于小说原文和大纲中的角色定位

只输出 JSON，不要输出任何解释性文字。`;
}

/**
 * 使用 skill 脚本生成 seed 骨架
 */
function generateSeed(outlinePath, workDir, skillDir) {
  const scriptPath = path.join(skillDir, 'scripts', 'novel-characters.mjs');
  if (!fileExistsNonEmpty(scriptPath)) {
    logger.warn('novel-characters.mjs 脚本不存在，手动构建 seed');
    return null;
  }

  logger.info('从大纲生成角色 seed 骨架...');
  const seedPath = path.join(workDir, 'seed.json');
  const result = runCommand(`node "${scriptPath}" seed "${outlinePath}" > "${seedPath}"`, {
    timeout: 60000,
  });

  if (result.success && fileExistsNonEmpty(seedPath)) {
    const seed = readJson(seedPath);
    logger.success(`seed 骨架已生成，包含 ${seed.characters?.length || 0} 个角色`);
    return seed;
  }

  logger.warn(`seed 生成失败: ${truncate(result.error || result.stderr, 300)}`);
  return null;
}

/**
 * 从大纲手动构建角色清单
 */
function buildCharacterListFromOutline(outlinePath) {
  const outline = readJson(outlinePath);
  const characters = outline.characters || [];
  return characters.map((c) => ({
    id: c.id,
    name: c.name,
    aliases: c.aliases || [],
    importance: c.tier === 'lead' ? 'protagonist' : c.tier === 'support' ? 'supporting' : 'minor',
    seedNote: `${c.role || ''} ${c.from || ''}`.trim(),
    persona: { arc: c.arc || '' },
  }));
}

/**
 * 为单个角色生成详细设定卡
 */
async function generateCharacterCard({ character, bookExcerpt, allCharacterNames, workDir, skillDir, lang }) {
  const profilePassPath = path.join(skillDir, 'references', 'profile-pass.md');
  const schemaPath = path.join(skillDir, 'references', 'schema.md');
  const profilePassContent = fileExistsNonEmpty(profilePassPath) ? readText(profilePassPath) : '';
  const schemaContent = fileExistsNonEmpty(schemaPath) ? readText(schemaPath) : '';

  const systemPrompt = buildCharacterSystemPrompt(profilePassContent, schemaContent);

  const userPrompt = `## 角色基础信息
- 角色ID：${character.id}
- 姓名：${character.name}
- 别名：${(character.aliases || []).join('、') || '无'}
- 重要性：${character.importance}
- 角色定位：${character.seedNote || '未指定'}
- 人物弧光：${character.persona?.arc || '未指定'}

## 同批其他角色（避免撞车）
${allCharacterNames.filter((n) => n !== character.name).join('、')}

## 小说原文参考
${bookExcerpt}

## 任务
请为角色「${character.name}」生成完整的设定卡，包含：
1. id（保持原样：${character.id}）
2. name（保持原样：${character.name}）
3. aliases（别名数组）
4. oneLiner（一句话人物概括，${lang === 'zh' ? '中文' : '目标语言'}）
5. persona：{ background, personality, arc, speakingStyle, motivation, fear }（${lang === 'zh' ? '中文' : '目标语言'}）
6. image：{ sheet（设定图版面指令，英文）, appearance（外貌提示词，英文）, costume（服装提示词，英文）, vibe（气质提示词，英文） }（全部英文，不含人名）
7. voice：{ description（音色描述，英文）, pace（语速，英文）, tone（语气，英文） }（全部英文）

只输出该角色的 JSON 对象。`;

  const card = await chatCompleteJson([
    { role: 'system', content: systemPrompt },
    { role: 'user', content: userPrompt },
  ], { temperature: 0.7, maxTokens: 8000 });

  // 确保 id 和 name 不变
  card.id = character.id;
  card.name = character.name;

  const slug = slugify(character.name) || character.id;
  const cardPath = path.join(workDir, `card-${slug}.json`);
  writeJson(cardPath, card);

  return card;
}

/**
 * 使用 skill 脚本 assemble 合成 cast.json
 */
function assembleCast(workDir, outputDir, bookName, skillDir, lang) {
  const scriptPath = path.join(skillDir, 'scripts', 'novel-characters.mjs');
  if (!fileExistsNonEmpty(scriptPath)) {
    return null;
  }

  const castPath = path.join(outputDir, `${bookName}-cast.json`);
  logger.info('合成 cast.json...');

  const result = runCommand(
    `node "${scriptPath}" assemble "${workDir}" --source "${bookName}" --lang ${lang} --out "${castPath}"`,
    { timeout: 120000 }
  );

  if (result.success && fileExistsNonEmpty(castPath)) {
    logger.success('cast.json 合成成功');
    return castPath;
  }

  logger.warn(`assemble 失败: ${truncate(result.error || result.stderr, 500)}`);
  return null;
}

/**
 * 手动合成 cast.json（assemble 失败时的后备方案）
 */
function manualAssemble(workDir, outputDir, bookName, characterList, lang) {
  logger.info('使用手动方式合成 cast.json...');
  const cards = [];

  for (const char of characterList) {
    const slug = slugify(char.name) || char.id;
    const cardPath = path.join(workDir, `card-${slug}.json`);
    if (fileExistsNonEmpty(cardPath)) {
      cards.push(readJson(cardPath));
    }
  }

  const cast = {
    meta: { source: bookName, lang, createdAt: new Date().toISOString() },
    characters: cards,
    summary: `共 ${cards.length} 个角色`,
  };

  const castPath = path.join(outputDir, `${bookName}-cast.json`);
  writeJson(castPath, cast);
  logger.success(`手动合成 cast.json 成功（${cards.length} 个角色）`);
  return castPath;
}

/**
 * 校验角色设定
 */
function validateCast(castPath, bookPath, skillDir) {
  const scriptPath = path.join(skillDir, 'scripts', 'novel-characters.mjs');
  if (!fileExistsNonEmpty(scriptPath)) {
    logger.warn('novel-characters.mjs 脚本不存在，跳过校验');
    return true;
  }

  logger.info('运行角色设定质量门校验...');
  const result = runCommand(`node "${scriptPath}" validate "${castPath}" "${bookPath}" --lang zh`, {
    timeout: 120000,
  });

  if (result.success) {
    logger.success('角色设定质量门校验通过');
    return true;
  }

  logger.warn(`角色设定校验未通过（将继续输出）: ${truncate(result.error || result.stderr, 500)}`);
  return false;
}

/**
 * 渲染角色设定输出
 */
function renderCast(castPath, outputDir, bookName, skillDir) {
  const scriptPath = path.join(skillDir, 'scripts', 'novel-characters.mjs');
  if (!fileExistsNonEmpty(scriptPath)) {
    logger.warn('novel-characters.mjs 脚本不存在，跳过渲染');
    return;
  }

  logger.info('渲染角色设定输出...');

  const mdResult = runCommand(
    `node "${scriptPath}" render "${castPath}" --md --lang zh > "${path.join(outputDir, `${bookName}-cast.md`)}"`,
    { timeout: 120000 }
  );
  if (mdResult.success) logger.success('角色设定 Markdown 已生成');

  const htmlResult = runCommand(
    `node "${scriptPath}" render "${castPath}" --html --lang zh > "${path.join(outputDir, 'cast-report.html')}"`,
    { timeout: 120000 }
  );
  if (htmlResult.success) logger.success('角色设定 HTML 报告已生成');
}

/**
 * 主入口
 */
export async function runCharactersPipeline(options) {
  const {
    outlinePath,
    bookPath,
    bookText,
    bookName,
    outputDir,
    skillDir,
    lang = 'zh',
    maxCharacters = 30,
  } = options;

  logger.setPrefix('角色');
  const workDir = path.join(outputDir, 'work-characters');
  ensureDir(workDir);
  ensureDir(outputDir);

  try {
    writeStatus(outputDir, 'characters', 'running', { startedAt: new Date().toISOString() });

    // Step 1: 生成或构建角色清单
    let characterList = [];
    const seed = generateSeed(outlinePath, workDir, skillDir);
    if (seed && seed.characters) {
      characterList = seed.characters;
    } else {
      characterList = buildCharacterListFromOutline(outlinePath);
    }

    // 限制角色数量
    if (characterList.length > maxCharacters) {
      logger.info(`角色数 ${characterList.length} 超过上限 ${maxCharacters}，取前 ${maxCharacters} 位`);
      characterList = characterList.slice(0, maxCharacters);
    }
    logger.info(`待生成角色数：${characterList.length}`);

    // Step 2: 准备小说摘录（截取相关部分）
    const maxExcerpt = 30000;
    const bookExcerpt = bookText.length > maxExcerpt
      ? bookText.slice(0, maxExcerpt) + '\n...（原文已截取）'
      : bookText;

    const allNames = characterList.map((c) => c.name);

    // Step 3: 逐个生成角色卡
    const cards = [];
    for (let i = 0; i < characterList.length; i++) {
      const char = characterList[i];
      logger.step(i + 1, characterList.length, `生成角色「${char.name}」设定卡...`);
      try {
        const card = await generateCharacterCard({
          character: char,
          bookExcerpt,
          allCharacterNames: allNames,
          workDir,
          skillDir,
          lang,
        });
        cards.push(card);
      } catch (err) {
        logger.error(`  角色「${char.name}」生成失败: ${err.message}`);
        // 写入最小占位卡
        const placeholder = {
          id: char.id,
          name: char.name,
          aliases: char.aliases || [],
          oneLiner: '生成失败，待补充',
          importance: char.importance || 'minor',
          persona: { background: '', personality: '', arc: char.persona?.arc || '', speakingStyle: '', motivation: '', fear: '' },
          image: { sheet: '', appearance: '', costume: '', vibe: '' },
          voice: { description: '', pace: '', tone: '' },
        };
        const slug = slugify(char.name) || char.id;
        writeJson(path.join(workDir, `card-${slug}.json`), placeholder);
        cards.push(placeholder);
      }
    }

    // Step 4: 合成 cast.json
    let castPath = assembleCast(workDir, outputDir, bookName, skillDir, lang);
    if (!castPath) {
      castPath = manualAssemble(workDir, outputDir, bookName, characterList, lang);
    }

    // Step 5: 校验
    const valid = validateCast(castPath, bookPath, skillDir);

    // Step 6: 渲染
    renderCast(castPath, outputDir, bookName, skillDir);

    writeStatus(outputDir, 'characters', 'completed', {
      finishedAt: new Date().toISOString(),
      castPath,
      characterCount: cards.length,
      validationPassed: valid,
    });

    return { castPath, success: true, validationPassed: valid };
  } catch (err) {
    logger.error(`角色设定生成失败: ${err.message}`);
    writeStatus(outputDir, 'characters', 'failed', { error: err.message });
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

  if (!opts.outline || !opts.book || !opts.output || !opts.skill) {
    console.error('用法: node pipeline-characters.mjs --outline <outline.json> --book <小说文本> --output <输出目录> --skill <skill目录> [--name 书名]');
    process.exit(1);
  }

  const bookText = readText(opts.book);
  runCharactersPipeline({
    outlinePath: opts.outline,
    bookPath: opts.book,
    bookText,
    bookName: opts.name || '改编作品',
    outputDir: opts.output,
    skillDir: opts.skill,
  }).then(() => {
    console.log('角色设定流水线执行完成');
  }).catch((err) => {
    console.error('角色设定流水线执行失败:', err);
    process.exit(1);
  });
}
