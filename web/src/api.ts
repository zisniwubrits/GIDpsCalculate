/**
 * 后端接口封装。
 *
 * 开发时 Vite 把 `/api` 代理到 Python 后端；生产由后端托管 dist，路径相同。
 */
import type { EvaluateResult, GraphJSON, Schema } from "./types";

const JSON_HEADERS = { "Content-Type": "application/json; charset=utf-8" };

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (body && typeof body.error === "string" && body.error) return body.error;
  } catch {
    /* 非 JSON 响应，走下面的兜底 */
  }
  return `HTTP ${res.status} ${res.statusText}`;
}

async function getJSON<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as T;
}

async function postJSON<T>(url: string, payload: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) throw new Error(await readError(res));
  return (await res.json()) as T;
}

/** 卡片类型 / 菜单分组 / 预设 / 参考表（前端渲染的单一数据源）。 */
export function fetchSchema(signal?: AbortSignal): Promise<Schema> {
  return getJSON<Schema>("/api/schema", signal);
}

/** F1 教程文本。 */
export function fetchHelp(signal?: AbortSignal): Promise<{ text: string; sections: string[] }> {
  return getJSON<{ text: string; sections: string[] }>("/api/help", signal);
}

/** 把整张图交给后端求值，拿回变量表 + 每个卡片的输出 + 最终结果。 */
export function evaluateGraph(
  graph: GraphJSON,
  signal?: AbortSignal,
): Promise<EvaluateResult> {
  return postJSON<EvaluateResult>("/api/evaluate", graph, signal);
}

/** 生成可读文本报告（导出结果用）。 */
export function buildReport(
  graph: GraphJSON,
  opts: { title?: string; filename?: string } = {},
  signal?: AbortSignal,
): Promise<{ ok: boolean; text: string; filename: string }> {
  return postJSON<{ ok: boolean; text: string; filename: string }>(
    "/api/report",
    { ...graph, ...opts },
    signal,
  );
}

export function health(signal?: AbortSignal): Promise<{
  ok: boolean;
  version: string;
  webBuilt: boolean;
}> {
  return getJSON("/api/health", signal);
}
