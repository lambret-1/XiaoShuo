#!/usr/bin/env node
/**
 * 小说转漫剧全流程流水线总控
 * 按顺序执行：大纲 → 角色 → 美术 → 剧本 → 分镜
 *
 * 用法：
 *   node pipeline-runner.mjs \
 *     --book <小说正文目录或合并文本> \
 *     --output <输出目录> \
 *     --skills <shuohao-skills 根目录> \
 *     [--name 书名] [--episodes 集数] [--duration 单集分钟] [--genre 题材]
 *     [--stage 从哪个阶段开始 outline|characters|art|script|storyboard]
 *     [--skip-validation] [--max-chars 角色上限]
 */

import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { runOutlinePipeline } from './pipeline-outline.mjs';
import { runCharactersPipeline } from './pipeline-characters.mjs';
import { runArtPipeline } from './pipeline-art.mjs';
import { runScriptPipeline } from './pipeline-script.mjs';
import { runStoryboardPipeline } from './pipeline-storyboard.mjs';
import {
  ensureDir, readText, writeText, writeJson, mergeChapters,
  logger, timestamp, fileExistsNonEmpty,
} from './pipeline-common.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const STAGES = ['outline', 'characters', 'art', 'script', 'storyboard'];
const STAGE_NAMES = {
  outline: '改编大纲',
  characters: '角色设定',
  art: '美术资产',
  script: '漫剧剧本',
  storyboard: '分镜',
};

/**
 * 解析命令行参数
 */
function parseArgs() {
  const args = process.argv.slice(2);
  const opts = {};
  for (let i = 0; i < args.length; i += 2) {
    const key = args[i].replace(/^--/, '');
    opts[key] = args[i + 1];
  }
  return opts;
}

/**
 * 准备小说输入：如果是目录则合并章节，如果是文件则直接使用
 */
function prepareBookInput(bookPath, workDir) {
  const bookTxtPath = path.join(workDir, 'book-full.txt');

  if (fs.statSync(bookPath).isDirectory()) {
    logger.info(`检测到章节目录，正在合并所有章节...`);
    const result = mergeChapters(bookPath, bookTxtPath);
    logger.success(`已合并 ${result.fileCount} 章，共 ${result.totalChars} 字符`);
  } else {
    logger.info(`使用已合并的小说文本：${bookPath}`);
    const content = readText(bookPath);
    writeText(bookTxtPath, content);
    logger.info(`文本长度：${content.length} 字符`);
  }

  return bookTxtPath;
}

/**
 * 检查上游产物是否存在
 */
function checkUpstream(outputDir, bookName, stage) {
  const required = {
    characters: [`${bookName}-outline.json`],
    art: [`${bookName}-outline.json`],
    script: [`${bookName}-outline.json`],
    storyboard: [`${bookName}-outline.json`, `${bookName}-script.json`],
  };

  const files = required[stage] || [];
  for (const f of files) {
    const p = path.join(outputDir, f);
    if (!fileExistsNonEmpty(p)) {
      throw new Error(`阶段「${STAGE_NAMES[stage]}」需要上游产物 ${f}，但文件不存在或为空。请先运行前置阶段。`);
    }
  }
}

/**
 * 主函数
 */
async function main() {
  const opts = parseArgs();

  if (!opts.book || !opts.output || !opts.skills) {
    console.error('用法: node pipeline-runner.mjs --book <小说目录或文本> --output <输出目录> --skills <shuohao-skills根目录>');
    console.error('可选参数: --name 书名 --episodes 集数 --duration 单集分钟 --genre 题材 --stage 起始阶段 --max-chars 角色上限');
    process.exit(1);
  }

  const bookName = opts.name || '改编作品';
  const outputDir = path.resolve(opts.output);
  const skillsRoot = path.resolve(opts.skills);
  const startStage = opts.stage || 'outline';
  const maxChars = parseInt(opts['max-chars'] || '30', 10);

  const workDir = path.join(outputDir, '_work');
  ensureDir(outputDir);
  ensureDir(workDir);

  logger.setPrefix('总控');
  logger.info(`========================================`);
  logger.info(`小说转漫剧全流程流水线`);
  logger.info(`========================================`);
  logger.info(`书名：${bookName}`);
  logger.info(`输出目录：${outputDir}`);
  logger.info(`Skill 根目录：${skillsRoot}`);
  logger.info(`起始阶段：${STAGE_NAMES[startStage]}（${startStage}）`);
  logger.info(`角色上限：${maxChars}`);
  logger.info(`开始时间：${timestamp()}`);
  logger.info(`========================================`);

  // 验证 skill 目录
  for (const stage of STAGES) {
    const skillDir = path.join(skillsRoot, 'skills', `novel-${stage}`);
    if (!fs.existsSync(skillDir)) {
      logger.warn(`Skill 目录不存在：${skillDir}`);
    }
  }

  // 准备小说输入
  let bookPath;
  let bookText = '';
  if (startStage === 'outline') {
    bookPath = prepareBookInput(path.resolve(opts.book), workDir);
    bookText = readText(bookPath);
  } else {
    // 从中间阶段开始，尝试找到已合并的文本
    bookPath = path.join(workDir, 'book-full.txt');
    if (fileExistsNonEmpty(bookPath)) {
      bookText = readText(bookPath);
      logger.info(`使用已有的合并文本：${bookPath}`);
    } else {
      // 尝试从输入参数获取
      if (opts.book && fs.existsSync(path.resolve(opts.book))) {
        bookPath = prepareBookInput(path.resolve(opts.book), workDir);
        bookText = readText(bookPath);
      }
    }
  }

  // 记录流水线配置
  const pipelineConfig = {
    bookName,
    outputDir,
    skillsRoot,
    startStage,
    params: {
      episodes: opts.episodes || 60,
      duration: opts.duration || 3,
      genre: opts.genre || '都市悬疑',
      adaptation: opts.adaptation || '抽核',
      maxChars,
    },
    startedAt: timestamp(),
    stages: {},
  };
  writeJson(path.join(outputDir, 'pipeline-config.json'), pipelineConfig);

  // 确定要执行的阶段
  const startIdx = STAGES.indexOf(startStage);
  if (startIdx === -1) {
    console.error(`无效的起始阶段：${startStage}，可选：${STAGES.join(', ')}`);
    process.exit(1);
  }
  const stagesToRun = STAGES.slice(startIdx);

  // 路径定义
  const outlinePath = path.join(outputDir, `${bookName}-outline.json`);
  const castPath = path.join(outputDir, `${bookName}-cast.json`);
  const artPath = path.join(outputDir, `${bookName}-art.json`);
  const scriptPath = path.join(outputDir, `${bookName}-script.json`);
  const storyboardPath = path.join(outputDir, `${bookName}-storyboard.json`);

  const results = {};
  const overallStart = Date.now();

  try {
    // 阶段 1：大纲
    if (stagesToRun.includes('outline')) {
      logger.info(`\n========== 阶段 1/5：${STAGE_NAMES.outline} ==========`);
      const skillDir = path.join(skillsRoot, 'skills', 'novel-outline');
      const result = await runOutlinePipeline({
        bookText,
        bookName,
        episodes: opts.episodes || 60,
        duration: opts.duration || 3,
        genre: opts.genre || '都市悬疑',
        adaptation: opts.adaptation || '抽核',
        outputDir,
        skillDir,
      });
      results.outline = result;
    } else {
      checkUpstream(outputDir, bookName, 'outline');
    }

    // 阶段 2：角色
    if (stagesToRun.includes('characters')) {
      logger.info(`\n========== 阶段 2/5：${STAGE_NAMES.characters} ==========`);
      const skillDir = path.join(skillsRoot, 'skills', 'novel-characters');
      const result = await runCharactersPipeline({
        outlinePath,
        bookPath,
        bookText,
        bookName,
        outputDir,
        skillDir,
        maxCharacters: maxChars,
      });
      results.characters = result;
    } else if (startStage !== 'outline') {
      checkUpstream(outputDir, bookName, 'characters');
    }

    // 阶段 3：美术
    if (stagesToRun.includes('art')) {
      logger.info(`\n========== 阶段 3/5：${STAGE_NAMES.art} ==========`);
      const skillDir = path.join(skillsRoot, 'skills', 'novel-art');
      const result = await runArtPipeline({
        outlinePath,
        castPath: fileExistsNonEmpty(castPath) ? castPath : null,
        bookName,
        outputDir,
        skillDir,
      });
      results.art = result;
    } else if (startStage !== 'outline' && startStage !== 'characters') {
      checkUpstream(outputDir, bookName, 'art');
    }

    // 阶段 4：剧本
    if (stagesToRun.includes('script')) {
      logger.info(`\n========== 阶段 4/5：${STAGE_NAMES.script} ==========`);
      const skillDir = path.join(skillsRoot, 'skills', 'novel-script');
      const result = await runScriptPipeline({
        outlinePath,
        artPath: fileExistsNonEmpty(artPath) ? artPath : null,
        castPath: fileExistsNonEmpty(castPath) ? castPath : null,
        bookName,
        outputDir,
        skillDir,
      });
      results.script = result;
    } else if (!['outline', 'characters', 'art'].includes(startStage)) {
      checkUpstream(outputDir, bookName, 'script');
    }

    // 阶段 5：分镜
    if (stagesToRun.includes('storyboard')) {
      logger.info(`\n========== 阶段 5/5：${STAGE_NAMES.storyboard} ==========`);
      const skillDir = path.join(skillsRoot, 'skills', 'novel-storyboard');
      const result = await runStoryboardPipeline({
        scriptPath,
        outlinePath,
        artPath: fileExistsNonEmpty(artPath) ? artPath : null,
        castPath: fileExistsNonEmpty(castPath) ? castPath : null,
        bookName,
        outputDir,
        skillDir,
      });
      results.storyboard = result;
    }

    // 完成总结
    const totalMinutes = ((Date.now() - overallStart) / 60000).toFixed(1);
    logger.info(`\n========================================`);
    logger.success(`全流程流水线执行完成！`);
    logger.info(`总耗时：${totalMinutes} 分钟`);
    logger.info(`完成时间：${timestamp()}`);
    logger.info(`========================================`);
    logger.info(`产物清单：`);

    const artifacts = [
      { name: '改编大纲', path: outlinePath, md: `${bookName}-outline.md`, html: 'outline-report.html' },
      { name: '角色设定', path: castPath, md: `${bookName}-cast.md`, html: 'cast-report.html' },
      { name: '美术资产', path: artPath, md: `${bookName}-art.md`, html: 'art-report.html' },
      { name: '漫剧剧本', path: scriptPath, md: `${bookName}-script.md`, html: 'script-report.html' },
      { name: '分镜表', path: storyboardPath, md: `${bookName}-storyboard.md`, html: 'storyboard-report.html' },
    ];

    for (const art of artifacts) {
      const exists = fileExistsNonEmpty(art.path);
      const size = exists ? fs.statSync(art.path).size : 0;
      logger.info(`  ${exists ? '✓' : '✗'} ${art.name}: ${path.basename(art.path)} (${(size / 1024).toFixed(1)} KB)`);
    }

    // 写入最终状态
    const finalConfig = readJson(path.join(outputDir, 'pipeline-config.json'));
    finalConfig.finishedAt = timestamp();
    finalConfig.totalDurationMinutes = parseFloat(totalMinutes);
    finalConfig.results = results;
    writeJson(path.join(outputDir, 'pipeline-config.json'), finalConfig);

    logger.info(`\n所有产物已输出至：${outputDir}`);
    process.exit(0);
  } catch (err) {
    logger.error(`\n========================================`);
    logger.error(`流水线执行失败：${err.message}`);
    logger.error(`失败时间：${timestamp()}`);
    logger.error(`========================================`);
    console.error(err.stack);

    // 记录失败状态
    try {
      const finalConfig = readJson(path.join(outputDir, 'pipeline-config.json'));
      finalConfig.failedAt = timestamp();
      finalConfig.error = err.message;
      writeJson(path.join(outputDir, 'pipeline-config.json'), finalConfig);
    } catch (_) { /* 忽略 */ }

    process.exit(1);
  }
}

main();
