#!/usr/bin/env node
/**
 * AI API 通用客户端
 * 支持 OpenAI 兼容接口，用于流水线中调用大模型生成内容
 * 零依赖，仅使用 Node.js 标准库
 */

import https from 'node:https';
import http from 'node:http';
import { URL } from 'node:url';

const DEFAULT_API_URL = 'https://api.openai.com/v1';
const DEFAULT_MODEL = 'gpt-4o';
const DEFAULT_TIMEOUT = 300000; // 5 分钟
const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_TEMPERATURE = 0.7;
const DEFAULT_MAX_TOKENS = 8192;

/**
 * 从环境变量读取配置
 */
export function getConfig() {
  return {
    apiKey: process.env.AI_API_KEY || process.env.OPENAI_API_KEY || '',
    apiUrl: (process.env.AI_API_URL || process.env.OPENAI_API_URL || DEFAULT_API_URL).replace(/\/+$/, ''),
    model: process.env.AI_MODEL || process.env.OPENAI_MODEL || DEFAULT_MODEL,
    timeout: parseInt(process.env.AI_TIMEOUT || String(DEFAULT_TIMEOUT), 10),
    maxRetries: parseInt(process.env.AI_MAX_RETRIES || String(DEFAULT_MAX_RETRIES), 10),
    temperature: parseFloat(process.env.AI_TEMPERATURE || String(DEFAULT_TEMPERATURE)),
    maxTokens: parseInt(process.env.AI_MAX_TOKENS || String(DEFAULT_MAX_TOKENS), 10),
  };
}

/**
 * 发送 HTTP 请求
 */
function httpRequest(urlStr, options, body) {
  return new Promise((resolve, reject) => {
    const url = new URL(urlStr);
    const lib = url.protocol === 'https:' ? https : http;
    const reqOptions = {
      hostname: url.hostname,
      port: url.port || (url.protocol === 'https:' ? 443 : 80),
      path: url.pathname + url.search,
      method: options.method || 'GET',
      headers: options.headers || {},
      timeout: options.timeout || DEFAULT_TIMEOUT,
    };

    const req = lib.request(reqOptions, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        resolve({ status: res.statusCode, headers: res.headers, body: data });
      });
    });

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy(new Error(`请求超时（${reqOptions.timeout}ms）`));
    });

    if (body) {
      req.write(body);
    }
    req.end();
  });
}

/**
 * 调用 Chat Completions API
 * @param {Array} messages - 消息数组 [{role, content}]
 * @param {Object} opts - 可选参数 {temperature, maxTokens, model}
 * @returns {Promise<string>} 模型回复文本
 */
export async function chatComplete(messages, opts = {}) {
  const config = getConfig();
  if (!config.apiKey) {
    throw new Error('未配置 AI_API_KEY 环境变量，无法调用 AI 服务');
  }

  const model = opts.model || config.model;
  const temperature = opts.temperature !== undefined ? opts.temperature : config.temperature;
  const maxTokens = opts.maxTokens || config.maxTokens;
  const maxRetries = opts.maxRetries || config.maxRetries;

  const requestBody = JSON.stringify({
    model,
    messages,
    temperature,
    max_tokens: maxTokens,
    response_format: opts.responseFormat || undefined,
  });

  let lastError = null;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const res = await httpRequest(`${config.apiUrl}/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${config.apiKey}`,
        },
        timeout: config.timeout,
      }, requestBody);

      if (res.status >= 200 && res.status < 300) {
        const data = JSON.parse(res.body);
        const content = data.choices?.[0]?.message?.content;
        if (!content) {
          throw new Error('AI 回复内容为空');
        }
        return content;
      }

      if (res.status === 429 || res.status >= 500) {
        lastError = new Error(`AI 服务返回 ${res.status}: ${res.body.slice(0, 500)}`);
        const waitMs = Math.min(2000 * attempt, 30000);
        console.error(`[AI 客户端] 第 ${attempt}/${maxRetries} 次尝试失败（${res.status}），${waitMs}ms 后重试...`);
        await new Promise((r) => setTimeout(r, waitMs));
        continue;
      }

      throw new Error(`AI 服务返回 ${res.status}: ${res.body.slice(0, 1000)}`);
    } catch (err) {
      lastError = err;
      if (attempt < maxRetries) {
        const waitMs = Math.min(2000 * attempt, 30000);
        console.error(`[AI 客户端] 第 ${attempt}/${maxRetries} 次请求异常: ${err.message}，${waitMs}ms 后重试...`);
        await new Promise((r) => setTimeout(r, waitMs));
      }
    }
  }

  throw lastError || new Error('AI 调用失败');
}

/**
 * 从 AI 回复中提取 JSON
 * 支持纯 JSON、```json 代码块、以及包含 JSON 的文本
 */
export function extractJson(text) {
  if (!text) return null;

  // 尝试直接解析
  try {
    return JSON.parse(text.trim());
  } catch (_) { /* 继续尝试其他方式 */ }

  // 尝试提取 ```json ... ``` 代码块
  const jsonBlockMatch = text.match(/```(?:json)?\s*([\s\S]*?)\s*```/i);
  if (jsonBlockMatch) {
    try {
      return JSON.parse(jsonBlockMatch[1].trim());
    } catch (_) { /* 继续 */ }
  }

  // 尝试提取第一个 { 到最后一个 } 之间的内容
  const firstBrace = text.indexOf('{');
  const lastBrace = text.lastIndexOf('}');
  if (firstBrace !== -1 && lastBrace > firstBrace) {
    try {
      return JSON.parse(text.slice(firstBrace, lastBrace + 1).trim());
    } catch (_) { /* 继续 */ }
  }

  // 尝试提取第一个 [ 到最后一个 ] 之间的内容
  const firstBracket = text.indexOf('[');
  const lastBracket = text.lastIndexOf(']');
  if (firstBracket !== -1 && lastBracket > firstBracket) {
    try {
      return JSON.parse(text.slice(firstBracket, lastBracket + 1).trim());
    } catch (_) { /* 继续 */ }
  }

  return null;
}

/**
 * 调用 AI 并期望返回 JSON
 * @param {Array} messages - 消息数组
 * @param {Object} opts - 可选参数
 * @returns {Promise<Object>} 解析后的 JSON 对象
 */
export async function chatCompleteJson(messages, opts = {}) {
  const content = await chatComplete(messages, {
    ...opts,
    responseFormat: opts.responseFormat || { type: 'json_object' },
  });
  const parsed = extractJson(content);
  if (!parsed) {
    throw new Error(`无法从 AI 回复中解析 JSON。回复前 500 字符: ${content.slice(0, 500)}`);
  }
  return parsed;
}

// 命令行测试入口
if (import.meta.url === `file://${process.argv[1]}`) {
  const testMsg = process.argv[2] || '你好，请用一句话介绍你自己';
  console.log(`[测试] 发送消息: ${testMsg}`);
  chatComplete([{ role: 'user', content: testMsg }])
    .then((reply) => {
      console.log('[测试] 收到回复:');
      console.log(reply);
    })
    .catch((err) => {
      console.error('[测试] 失败:', err.message);
      process.exit(1);
    });
}
