/**
 * 画布模型与纯函数工具（与旧版 tkinter 的落位/对齐规则保持一致）。
 *
 * 这里只处理「数据」，不碰 React / React Flow，方便单测。
 */
import type { CardNode, Fields, GraphJSON, GraphLinkJSON, PresetItem, Schema } from "./types";

export const ZOOM_MIN = 0.25;
export const ZOOM_MAX = 2.5;

/**
 * 卡片只有「标题栏」能拖动（用户明确要求：只能拖标题栏，标题栏大小不动）。
 *
 * 这是 React Flow 的 `node.dragHandle` 选择器：必须能匹配到卡片里的标题栏元素
 * （CardNode 里的 `.card-head`），否则卡片会彻底拖不动。
 * 标题栏里的按钮另有 `nodrag` 类，点它们不会进入拖动。
 */
export const CARD_DRAG_HANDLE = ".card-head";

/** 卡片未测量前的估算尺寸（用于落位与对齐）。 */
export const EST_W = 300;
export const EST_H = 210;

export type SizeOf = (node: CardNode) => { w: number; h: number };

export const estimateSize: SizeOf = (node) => ({
  w: node.size?.[0] ?? node.measured?.width ?? EST_W,
  h: node.size?.[1] ?? node.measured?.height ?? EST_H,
});

/** 生成不重复的节点 id：n1、n2… */
export function nextNodeId(nodes: CardNode[]): string {
  let max = 0;
  for (const n of nodes) {
    const m = /^n(\d+)$/.exec(n.id);
    if (m) max = Math.max(max, Number(m[1]));
  }
  return `n${max + 1}`;
}

/** 按 schema 造一张新卡片（字段取默认值，可覆盖）。 */
export function makeNode(
  schema: Schema,
  type: string,
  pos: [number, number],
  id: string,
  overrides: Record<string, string> = {},
): CardNode {
  const spec = schema.nodeTypes[type];
  if (!spec) throw new Error(`未知卡片类型: ${type}`);
  const fields: Fields = { ...spec.defaults };
  for (const [k, v] of Object.entries(overrides)) {
    if (k in fields) fields[k] = v;
  }
  return {
    id,
    type,
    pos,
    size: null,
    font_size: null,
    inputs: spec.inputs,
    fields,
    collapsed: false,
  };
}

/** 一块矩形是否与已有卡片重叠（含 20px 间距）。 */
export function areaFree(
  nodes: CardNode[],
  x: number,
  y: number,
  w: number,
  h: number,
  sizeOf: SizeOf = estimateSize,
): boolean {
  for (const n of nodes) {
    const { w: bw, h: bh } = sizeOf(n);
    if (x < n.pos[0] + bw + 20 && n.pos[0] < x + w + 20 &&
        y < n.pos[1] + bh + 20 && n.pos[1] < y + h + 20) {
      return false;
    }
  }
  return true;
}

/** 新卡片落位：从左上开始找第一个不重叠的网格位置。 */
export function freeSlot(
  nodes: CardNode[],
  sizeOf: SizeOf = estimateSize,
): [number, number] {
  const cols = 4;
  const cw = 280;
  const ch = 250;
  for (let i = 0; i < 400; i += 1) {
    const x = 40 + (i % cols) * cw;
    const y = 60 + Math.floor(i / cols) * ch;
    if (areaFree(nodes, x, y, EST_W, EST_H, sizeOf)) return [x, y];
  }
  return [40, 60];
}

/** 为一串卡片找一块空白起始位置（从上往下扫描）。 */
export function chainOrigin(
  nodes: CardNode[],
  count: number,
  spacing = 350,
  x0 = 40,
  sizeOf: SizeOf = estimateSize,
): [number, number] {
  const w = Math.max(count - 1, 0) * spacing + 360;
  let y = 120;
  for (let i = 0; i < 400; i += 1) {
    if (areaFree(nodes, x0, y, w, 300, sizeOf)) return [x0, y];
    y += 300;
  }
  return [x0, y];
}

/** 预设链的横向排布：按真实宽度依次排开，避免压叠。 */
export function spreadChain(
  nodes: CardNode[],
  ids: string[],
  y: number,
  sizeOf: SizeOf = estimateSize,
): CardNode[] {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  let cx = byId.get(ids[0])?.pos[0] ?? 40;
  const moved = new Map<string, number>();
  for (const id of ids) {
    const node = byId.get(id);
    if (!node) continue;
    moved.set(id, cx);
    cx += Math.max(sizeOf(node).w, EST_W) + 40;
  }
  return nodes.map((n) =>
    moved.has(n.id) ? { ...n, pos: [moved.get(n.id) as number, y] } : n,
  );
}

/** 一键预设：造出整条链并连好线（**不含 ★结果**），放在空白位置。 */
export function addPreset(
  schema: Schema,
  name: string,
  nodes: CardNode[],
  links: GraphLinkJSON[],
  sizeOf: SizeOf = estimateSize,
): { nodes: CardNode[]; links: GraphLinkJSON[]; created: string[] } {
  const spec: PresetItem[] | undefined = schema.presets[name];
  if (!spec || spec.length === 0) {
    return { nodes, links, created: [] };
  }
  const [x0, y0] = chainOrigin(nodes, spec.length, 350, 40, sizeOf);
  const created: CardNode[] = [];
  const newLinks: GraphLinkJSON[] = [];
  let prev: string | null = null;
  let next = nodes;
  let cursor = x0;
  const idBase = (() => {
    let max = 0;
    for (const n of nodes) {
      const m = /^n(\d+)$/.exec(n.id);
      if (m) max = Math.max(max, Number(m[1]));
    }
    return max;
  })();
  spec.forEach((item, i) => {
    const id = `n${idBase + 1 + i}`;
    const node = makeNode(schema, item.type, [cursor, y0], id, item.fields);
    created.push(node);
    next = [...next, node];
    if (prev) newLinks.push({ src: prev, dst: id, port: 0 });
    prev = id;
    cursor += 320;
  });
  return {
    nodes: spreadChain(next, created.map((n) => n.id), y0, sizeOf),
    links: [...links, ...newLinks],
    created: created.map((n) => n.id),
  };
}

export type AlignMode = "left" | "top" | "hcenter" | "vcenter";

/** 对齐选中的卡片（与旧版一致：hcenter/vcenter 以包围盒中心为准）。 */
export function alignPositions(
  nodes: CardNode[],
  ids: string[],
  mode: AlignMode,
  sizeOf: SizeOf = estimateSize,
): Record<string, [number, number]> {
  const picked = nodes.filter((n) => ids.includes(n.id));
  if (picked.length < 2) return {};
  const boxes = picked.map((n) => {
    const { w, h } = sizeOf(n);
    return { id: n.id, x: n.pos[0], y: n.pos[1], w, h };
  });
  const lefts = boxes.map((b) => b.x);
  const tops = boxes.map((b) => b.y);
  const rights = boxes.map((b) => b.x + b.w);
  const bottoms = boxes.map((b) => b.y + b.h);
  const out: Record<string, [number, number]> = {};
  if (mode === "left") {
    const tx = Math.min(...lefts);
    for (const b of boxes) out[b.id] = [tx, b.y];
  } else if (mode === "top") {
    const ty = Math.min(...tops);
    for (const b of boxes) out[b.id] = [b.x, ty];
  } else if (mode === "hcenter") {
    const cx = (Math.min(...lefts) + Math.max(...rights)) / 2;
    for (const b of boxes) out[b.id] = [cx - b.w / 2, b.y];
  } else {
    const cy = (Math.min(...tops) + Math.max(...bottoms)) / 2;
    for (const b of boxes) out[b.id] = [b.x, cy - b.h / 2];
  }
  return out;
}

/** 加一条连线会不会形成环（src 的输出最终流回 src）。 */
export function wouldCycle(
  links: GraphLinkJSON[],
  src: string,
  dst: string,
): boolean {
  if (src === dst) return true;
  const seen = new Set<string>();
  const stack = [dst];
  while (stack.length) {
    const cur = stack.pop() as string;
    if (cur === src) return true;
    if (seen.has(cur)) continue;
    seen.add(cur);
    for (const l of links) {
      if (l.src === cur) stack.push(l.dst);
    }
  }
  return false;
}

/** 加/替换一条连线（同一个输入端口只保留最后一条）。 */
export function connect(
  links: GraphLinkJSON[],
  src: string,
  dst: string,
  port: number,
): GraphLinkJSON[] {
  const kept = links.filter((l) => !(l.dst === dst && l.port === port));
  return [...kept, { src, dst, port }];
}

/** 节点 + 连线 → 工程 JSON（与后端 / 旧版 tkinter 完全兼容）。 */
export function graphToJSON(
  nodes: CardNode[],
  links: GraphLinkJSON[],
  zoom: number,
  name: string,
): GraphJSON {
  return {
    version: 1,
    app: "GenshinDamageCalc",
    zoom,
    name,
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.type,
      pos: [n.pos[0], n.pos[1]],
      size: n.size ? [n.size[0], n.size[1]] : null,
      font_size: n.font_size,
      inputs: n.inputs,
      fields: { ...n.fields },
      collapsed: Boolean(n.collapsed),
    })),
    links: links.map((l) => ({ src: l.src, dst: l.dst, port: l.port })),
  };
}

/** 工程 JSON → 节点 + 连线（跳过未知类型与悬空连线，兼容旧存档）。 */
export function jsonToGraph(
  data: unknown,
  schema: Schema,
): { nodes: CardNode[]; links: GraphLinkJSON[]; zoom: number; name: string } {
  const raw = (data ?? {}) as Partial<GraphJSON>;
  const nodes: CardNode[] = [];
  const ids = new Set<string>();
  const list = Array.isArray(raw.nodes) ? raw.nodes : [];
  list.forEach((nd, i) => {
    if (!nd || typeof nd !== "object") return;
    const type = String((nd as GraphJSON["nodes"][number]).type ?? "");
    if (!schema.nodeTypes[type]) return;
    const id = String((nd as { id?: unknown }).id ?? `n${i + 1}`);
    if (ids.has(id)) return;
    ids.add(id);
    const pos = (nd as { pos?: unknown }).pos;
    const px = Array.isArray(pos) && Number.isFinite(Number(pos[0])) ? Number(pos[0]) : 40;
    const py = Array.isArray(pos) && Number.isFinite(Number(pos[1])) ? Number(pos[1]) : 60;
    const size = (nd as { size?: unknown }).size;
    const okSize =
      Array.isArray(size) && Number(size[0]) > 0 && Number(size[1]) > 0
        ? ([Number(size[0]), Number(size[1])] as [number, number])
        : null;
    const spec = schema.nodeTypes[type];
    const fields: Fields = { ...spec.defaults };
    const incoming = (nd as { fields?: Record<string, unknown> }).fields ?? {};
    for (const f of [...spec.fields, ...spec.hidden_fields.map((k) => ({ key: k, kind: "text" as const }))]) {
      const v = incoming[f.key];
      if (v === undefined || v === null) continue;
      fields[f.key] = typeof v === "boolean" ? v : String(v);
    }
    // 端口数完全由卡片类型决定：旧存档里写过的 inputs 一律忽略（历史上只有加法卡片能改，
    // 且扩出来的端口实际连不上，见 genshin_dmg/nodes.py 里 add 卡的注释）。
    const inputs = spec.inputs;
    const rawFont = Number((nd as { font_size?: unknown }).font_size);
    nodes.push({
      id,
      type,
      pos: [px, py],
      size: okSize,
      font_size: Number.isFinite(rawFont) && rawFont > 0 ? rawFont : null,
      inputs,
      fields,
      collapsed: Boolean((nd as { collapsed?: unknown }).collapsed),
    });
  });
  const links: GraphLinkJSON[] = [];
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const rawLinks = Array.isArray(raw.links) ? raw.links : [];
  for (const l of rawLinks) {
    const src = String((l as { src?: unknown })?.src ?? "");
    const dst = String((l as { dst?: unknown })?.dst ?? "");
    if (!ids.has(src) || !ids.has(dst) || src === dst) continue;
    const port = Number((l as { port?: unknown })?.port ?? 0);
    // 端口号必须落在目标卡片真实的输入端口范围内（旧存档里多余的端口会被丢弃）
    const target = byId.get(dst);
    const maxPort = target ? target.inputs : 0;
    if (!Number.isFinite(port) || port < 0 || port >= maxPort) continue;
    links.push({ src, dst, port });
  }
  const zoomRaw = Number(raw.zoom);
  return {
    nodes,
    links,
    zoom: Number.isFinite(zoomRaw)
      ? Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, zoomRaw))
      : 1,
    name: typeof raw.name === "string" ? raw.name : "",
  };
}

/** 结果链上是否包含某类卡片（用于「没有暴击区」提示）。 */
export function chainTypes(
  nodes: CardNode[],
  links: GraphLinkJSON[],
): string[] {
  const result = nodes.find((n) => n.type === "result");
  if (!result) return [];
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const seen = new Set<string>();
  const out: string[] = [];
  const walk = (id: string) => {
    if (seen.has(id)) return;
    seen.add(id);
    const node = byId.get(id);
    if (!node) return;
    for (let p = 0; p < node.inputs; p += 1) {
      const link = links.find((l) => l.dst === id && l.port === p);
      if (link) walk(link.src);
    }
    out.push(node.type);
  };
  walk(result.id);
  return out;
}

/** 单值结果卡片上显示的绑定变量名。 */
export function boundNames(node: CardNode): string[] {
  return ["var_nc", "var_cr", "var_ex"]
    .map((k) => String(node.fields[k] ?? "").trim())
    .filter(Boolean);
}
