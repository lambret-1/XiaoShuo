#!/usr/bin/env node
/**
 * 流水线公共工具模块
 * 提供文件操作、日志、路径处理等通用功能
 */

import fs from 'node:fs';
import path from 'node:path';
import { execSync } from 'node:child_process';

/**
 * 确保目录存在
 */
export function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

/**
 * 读取 JSON 文件
 */
export function readJson(filePath) {
  const content = fs.readFileSync(filePath, 'utf-8');
  return JSON.parse(content);
}

/**
 * 写入 JSON 文件
 */
export function writeJson(filePath, data) {
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf-8');
}

/**
 * 读取文本文件
 */
export function readText(filePath) {
  return fs.readFileSync(filePath, 'utf-8');
}

/**
 * 写入文本文件
 */
export function writeText(filePath, content) {
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, content, 'utf-8');
}

/**
 * 递归列出目录下的文件
 */
export function listFiles(dirPath, extension = null) {
  const results = [];
  if (!fs.existsSync(dirPath)) return results;

  const items = fs.readdirSync(dirPath);
  for (const item of items) {
    const fullPath = path.join(dirPath, item);
    const stat = fs.statSync(fullPath);
    if (stat.isDirectory()) {
      results.push(...listFiles(fullPath, extension));
    } else if (!extension || item.endsWith(extension)) {
      results.push(fullPath);
    }
  }
  return results;
}

/**
 * 合并目录下所有 Markdown 章节文件为单一文本
 * 按文件名排序（支持第001章格式）
 */
export function mergeChapters(chaptersDir, outputPath) {
  const files = listFiles(chaptersDir, '.md')
    .filter((f) => path.basename(f).match(/^第\d+章/))
    .sort((a, b) => {
      const numA = parseInt(path.basename(a).match(/第(\d+)章/)?.[1] || '0', 10);
      const numB = parseInt(path.basename(b).match(/第(\d+)章/)?.[1] || '0', 10);
      return numA - numB;
    });

  let combined = '';
  for (const file of files) {
    const content = readText(file);
    const title = path.basename(file, '.md');
    combined += `\n\n# ${title}\n\n${content}\n`;
  }

  writeText(outputPath, combined.trim());
  return { fileCount: files.length, totalChars: combined.length, files };
}

/**
 * 执行 shell 命令并返回输出
 */
export function runCommand(command, options = {}) {
  const cwd = options.cwd || process.cwd();
  const env = { ...process.env, ...options.env };
  try {
    const output = execSync(command, {
      cwd,
      env,
      encoding: 'utf-8',
      stdio: options.stdio || 'pipe',
      timeout: options.timeout || 300000,
    });
    return { success: true, output };
  } catch (err) {
    return {
      success: false,
      error: err.message,
      stdout: err.stdout?.toString() || '',
      stderr: err.stderr?.toString() || '',
    };
  }
}

/**
 * 日志工具
 */
export const logger = {
  _prefix: '',
  setPrefix(p) { this._prefix = p; },
  info(msg) { console.log(`[${this._prefix}] ${msg}`); },
  warn(msg) { console.warn(`[${this._prefix}][警告] ${msg}`); },
  error(msg) { console.error(`[${this._prefix}][错误] ${msg}`); },
  success(msg) { console.log(`[${this._prefix}][成功] ${msg}`); },
  step(num, total, msg) { console.log(`[${this._prefix}] [${num}/${total}] ${msg}`); },
};

/**
 * 从文件路径中提取 slug（用于角色/场景命名）
 */
export function slugify(name) {
  return name
    .toLowerCase()
    .replace(/[^\w\u4e00-\u9fa5]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 50);
}

/**
 * 截断文本用于日志显示
 */
export function truncate(text, maxLen = 100) {
  if (!text) return '';
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text;
}

/**
 * 获取当前时间戳字符串（北京时间）
 */
export function timestamp() {
  const now = new Date();
  const utc = now.getTime() + now.getTimezoneOffset() * 60000;
  const bj = new Date(utc + 8 * 3600000);
  return bj.toISOString().replace('T', ' ').slice(0, 19) + ' CST';
}

/**
 * 写入流水线状态文件
 */
export function writeStatus(outputDir, stage, status, detail = {}) {
  const statusFile = path.join(outputDir, 'pipeline-status.json');
  let current = {};
  if (fs.existsSync(statusFile)) {
    try { current = readJson(statusFile); } catch (_) { current = {}; }
  }
  current[stage] = {
    status,
    updatedAt: timestamp(),
    ...detail,
  };
  writeJson(statusFile, current);
}

/**
 * 检查文件是否存在且非空
 */
export function fileExistsNonEmpty(filePath) {
  try {
    const stat = fs.statSync(filePath);
    return stat.isFile() && stat.size > 0;
  } catch (_) {
    return false;
  }
}
