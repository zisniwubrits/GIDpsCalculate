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

/** 当前工程目录（一键保存会写到这里；后端记住，从哪读就往哪存）。 */
export interface StorageInfo {
  dir: string;
  defaultDir: string;
  configFile: string;
  exists: boolean;
}

export function fetchStorage(signal?: AbortSignal): Promise<StorageInfo> {
  return getJSON<StorageInfo>("/api/storage", signal);
}

export interface SaveResult {
  ok: boolean;
  path: string;
  dir: string;
  filename: string;
}

/** 一键保存工程 JSON：后端直接写文件（覆盖同名），不再走浏览器下载。 */
export function saveProject(graph: GraphJSON, signal?: AbortSignal): Promise<SaveResult> {
  return postJSON<SaveResult>("/api/save/project", graph, signal);
}

/** 导出结果：后端生成报告并写成 <工程名>_<时间戳>.txt，返回文本与路径。 */
export function saveReport(
  graph: GraphJSON,
  opts: { title?: string } = {},
  signal?: AbortSignal,
): Promise<SaveResult & { text: string }> {
  return postJSON<SaveResult & { text: string }>("/api/report", { ...graph, ...opts }, signal);
}

export interface OpenResult {
  ok: boolean;
  /** 用户取消（或没有图形环境）时为 true */
  cancelled?: boolean;
  path?: string;
  dir?: string;
  graph?: GraphJSON;
  storage?: StorageInfo;
  error?: string;
}

/** 打开工程：后端弹本机原生对话框，读回内容并记住它所在目录。 */
export function openProject(signal?: AbortSignal): Promise<OpenResult> {
  return postJSON<OpenResult>("/api/open", {}, signal);
}

export function health(signal?: AbortSignal): Promise<{
  ok: boolean;
  version: string;
  webBuilt: boolean;
  /** 前端产物比源码旧（浏览器拿到的是旧界面）—— 界面据此提示重建 */
  webStale: boolean;
  webBuildTime: string | null;
  webSourceTime: string | null;
  webReason: string;
}> {
  return getJSON("/api/health", signal);
}
