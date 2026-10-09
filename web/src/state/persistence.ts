/** 工程自动存到浏览器本地（localStorage），刷新页面不丢。 */
import type { GraphJSON } from "../types";

const KEY = "genshin-dmg-calc:project:v1";

export interface StoredProject {
  graph: GraphJSON;
  savedAt: string;
}

export function loadLocal(): GraphJSON | null {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredProject | GraphJSON;
    const graph = (parsed as StoredProject).graph ?? (parsed as GraphJSON);
    if (!graph || typeof graph !== "object" || !Array.isArray(graph.nodes)) return null;
    return graph;
  } catch {
    return null;
  }
}

export function saveLocal(graph: GraphJSON): void {
  try {
    const payload: StoredProject = { graph, savedAt: new Date().toISOString() };
    window.localStorage.setItem(KEY, JSON.stringify(payload));
  } catch {
    /* 隐私模式 / 配额满：忽略，不影响使用 */
  }
}

export function clearLocal(): void {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    /* 忽略 */
  }
}
