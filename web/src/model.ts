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

/** 「角色」容器面板的默认尺寸（要够大才装得下几张卡） */
export const ROLE_W = 560;
export const ROLE_H = 380;

export type SizeOf = (node: CardNode) => { w: number; h: number };

export const estimateSize: SizeOf = (node) => {
  const isRole = isNamespaceNode(node);
  return {
    w: node.size?.[0] ?? node.measured?.width ?? (isRole ? ROLE_W : EST_W),
    h: node.size?.[1] ?? node.measured?.height ?? (isRole ? ROLE_H : EST_H),
  };
};

// ---------------------------------------------------------------- 角色命名空间
/**
 * 角色名合法性：它要能用进 `名字::变量` 的写法里，所以
 * 不能有空白、`:`（含 `::`）、连续下划线，且必须是「标识符」形态（不能数字开头）。
 * 后端还会用 Python 的 isidentifier 再判一次（后端是最终权威）。
 */
const ROLE_NAME_RE = /^[\p{L}\p{N}_]+$/u;

export function validRoleName(name: string): boolean {
  const t = (name ?? "").trim();
  if (!t || t !== name) return false;
  if (t.includes("__") || t.includes(":")) return false;
  if (!ROLE_NAME_RE.test(t)) return false;
  return !/^\p{N}/u.test(t);
}

/** 新建角色容器时的默认名：角色1、角色2…（跳过已占用的） */
export function nextRoleName(nodes: CardNode[]): string {
  const taken = new Set(
    nodes
      .filter((n) => isNamespaceNode(n))
      .map((n) => String(n.fields.role_name ?? "").trim()),
  );
  let i = 1;
  while (taken.has(`角色${i}`)) i += 1;
  return `角色${i}`;
}

export interface RoleBox {
  id: string;
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** 画布上所有有效的角色容器矩形（名字为空/非法的容器不参与归属判定）。 */
/**
 * 是不是**命名空间容器**（角色 / 武器）：它们的字段里一定有 `role_name`
 * （角色名 / 武器名）。这样前端不用硬编码卡片类型名。
 */
export function isNamespaceNode(node: CardNode): boolean {
  return Object.prototype.hasOwnProperty.call(node.fields ?? {}, "role_name");
}

/**
 * 是不是**带面板**的命名空间容器（角色）：武器没有面板。
 * 判据用 `panel_show`（控制面板显示哪些项的字段）—— 武器的字段里没有它。
 */
export function isPanelNode(node: CardNode): boolean {
  return (
    isNamespaceNode(node) && Object.prototype.hasOwnProperty.call(node.fields ?? {}, "panel_show")
  );
}

export function roleBoxes(nodes: CardNode[]): RoleBox[] {
  const out: RoleBox[] = [];
  for (const n of nodes) {
    if (!isNamespaceNode(n)) continue;
    const name = String(n.fields.role_name ?? "").trim();
    if (!validRoleName(name)) continue;
    const { w, h } = estimateSize(n);
    out.push({ id: n.id, name, x: n.pos[0], y: n.pos[1], w, h });
  }
  return out;
}

/** 某节点属于哪个角色：卡片中心落在哪个容器里（嵌套时取最小的那个）；否则返回 ""。 */
export function roleOfNode(node: CardNode, boxes: RoleBox[]): string {
  if (isNamespaceNode(node)) return ""; // 容器自身不属于任何角色
  const { w, h } = estimateSize(node);
  const cx = node.pos[0] + w / 2;
  const cy = node.pos[1] + h / 2;
  let best: RoleBox | null = null;
  for (const b of boxes) {
    if (cx < b.x || cx > b.x + b.w || cy < b.y || cy > b.y + b.h) continue;
    if (!best || b.w * b.h < best.w * best.h) best = b;
  }
  return best ? best.name : "";
}

/** 整张画布的「节点 id → 角色名」（给卡片徽标与求值载荷用）。 */
export function buildRoleMap(nodes: CardNode[]): Record<string, string> {
  const boxes = roleBoxes(nodes);
  const out: Record<string, string> = {};
  for (const n of nodes) out[n.id] = roleOfNode(n, boxes);
  return out;
}

/**
 * 框选时要不要**忽略**这张卡片的选中。
 * 角色容器是一大块面板，任意框选矩形几乎总会与它相交 —— 而 React Flow 的
 * `getNodesInside` 不看 `selectable`，所以框选一定把它一起选中（随后 Delete 会连
 * 面板一起删掉）。这条规则让「框选」不选中面板：想选它请点它的标题栏。
 */
export function ignoredByBoxSelect(node: CardNode): boolean {
  return isNamespaceNode(node);
}

// ------------------------------------------------- 一键隐藏区域内的卡片
/** 有没有开「隐藏区域内的卡片」（角色卡上的字段） */
export function cardsHidden(node: CardNode): boolean {
  return Boolean(node.fields?.cards_hidden);
}

/**
 * 哪些卡片因为所在角色开了「隐藏」而看不见。
 *
 * 隐藏是**界面状态**（不进 /api/evaluate 载荷，隐藏不改变计算结果），
 * 但跟着工程 JSON 存 —— 藏好的东西刷新后不该又冒出来。
 * 只作用于**非容器**卡片：同区域里嵌套的另一个角色标记仍然可见（还能点它、展开它）。
 */
export function hiddenCardsFor(nodes: CardNode[]): Set<string> {
  const out = new Set<string>();
  const hidden = nodes.filter(cardsHidden);
  if (!hidden.length) return out;
  const boxes = roleBoxes(nodes);
  for (const n of nodes) {
    if (isNamespaceNode(n)) continue;
    const owner = roleOfNode(n, boxes);
    if (owner && hidden.some((h) => String(h.fields.role_name ?? "").trim() === owner)) {
      out.add(n.id);
    }
  }
  return out;
}

/**
 * 右键「隐藏/显示区域内的卡片」：开隐藏时**顺手把状态切到另一头**
 * （用户要求：隐藏后只剩一张最小的牌子，折叠由调用方一起做）。
 * 返回新节点数组（纯函数，方便单测）。
 */
export function toggleRoleCardsHidden(nodes: CardNode[], id: string): CardNode[] {
  return nodes.map((n) =>
    n.id === id ? { ...n, fields: { ...n.fields, cards_hidden: !cardsHidden(n) } } : n,
  );
}

/** 区域内有多少张卡片（右键菜单里报个数；不含容器自己） */
export function cardsInside(nodes: CardNode[], id: string): number {
  const target = nodes.find((n) => n.id === id);
  const name = String(target?.fields.role_name ?? "").trim();
  if (!name) return 0;
  const boxes = roleBoxes(nodes);
  return nodes.filter((n) => !isNamespaceNode(n) && roleOfNode(n, boxes) === name).length;
}

/**
 * 「隐藏区域内的卡片」能不能做：区域内卡片**不能有连到区域外的连线**。
 *
 * 为什么（用户要求）：藏起区域内卡片时，跨区域的线会只剩半截、指向看不见的卡片。
 * 与其画一条断头线，不如直接拒绝隐藏，并说清是哪几张卡连到外面。
 * 返回**区域外那些卡片的 id**（空数组 = 允许隐藏），文案由调用方按 schema 拼。
 */
export function cardsBlockingHide(nodes: CardNode[], links: GraphLinkJSON[], id: string): string[] {
  const target = nodes.find((n) => n.id === id);
  const name = String(target?.fields.role_name ?? "").trim();
  if (!name) return [];
  const boxes = roleBoxes(nodes);
  const inside = new Set(
    nodes.filter((n) => !isNamespaceNode(n) && roleOfNode(n, boxes) === name).map((n) => n.id),
  );
  if (!inside.size) return [];
  const blocked: string[] = [];
  for (const l of links) {
    const cross =
      (inside.has(l.src) && !inside.has(l.dst)) || (inside.has(l.dst) && !inside.has(l.src));
    if (!cross) continue;
    const outsideId = inside.has(l.src) ? l.dst : l.src;
    if (!blocked.includes(outsideId)) blocked.push(outsideId);
  }
  return blocked;
}

// ---------------------------------------------------------------- schema 兜底
/**
 * 给后端 schema 补齐缺省结构。
 *
 * 为什么需要：前端新增界面时往往会用到新的 schema 字段（例如「角色面板」用的
 * `panelMacros`），而浏览器的 `/api/schema` 可能是**旧后端进程**给的 ——
 * 直接 `schema.panelMacros.map(...)` 就会抛异常，表现为**整页白屏**。
 * 这里统一补成空数组/空对象，让界面降级显示（并在用到的地方提示"后端版本过旧"）。
 */
export function normalizeSchema(raw: Schema | null | undefined): Schema | null {
  if (!raw || typeof raw !== "object") return null;
  const nodeTypes: Schema["nodeTypes"] = {};
  for (const [key, spec] of Object.entries(raw.nodeTypes ?? {})) {
    nodeTypes[key] = {
      ...spec,
      fields: spec?.fields ?? [],
      hidden_fields: spec?.hidden_fields ?? [],
      defaults: spec?.defaults ?? {},
    };
  }
  return {
    ...raw,
    groups: raw.groups ?? [],
    nodeTypes,
    presets: raw.presets ?? {},
    tables: raw.tables ?? {},
    resultVarFields: raw.resultVarFields ?? [],
    panelMacros: raw.panelMacros ?? [],
    panelCustomPattern: raw.panelCustomPattern ?? DEFAULT_PANEL_CUSTOM_PATTERN,
  };
}

// ---------------------------------------------------------------- 角色面板宏
/**
 * 角色面板里一行 ``名字 = 值``（与后端 split_var_line 同规则）。
 *
 * 分隔符按 ``=`` → ``：`` → ``:`` 的**先后**找，而不是找最靠前的那个：
 * ``out::gift = 40`` 里的第一个 ``:`` 属于命名空间 ``::``，不能当分隔符
 * （否则名字会被切成 ``out``）。
 */
function panelLines(text: string): [string, string][] {
  const out: [string, string][] = [];
  for (const raw of (text ?? "").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    for (const sep of ["=", "：", ":"]) {
      const i = line.indexOf(sep);
      if (i <= 0) continue;
      out.push([line.slice(0, i).trim(), line.slice(i + sep.length).trim()]);
      break;
    }
  }
  return out;
}

/**
 * 解析角色卡「面板」字段里的 ``宏 = 值`` 多行文本（与后端 split_var_line 同规则：
 * 认 ``=`` / ``：`` / ``:``，跳过空行与 ``#`` 注释，只保留词表里的宏）。
 */
export function parsePanel(text: string, keys: readonly string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of panelLines(text)) {
    if (!keys.includes(key)) continue;
    out[key] = value;
  }
  return out;
}

/** 反向：``{宏: 值}`` → 多行文本（空值不写；顺序按词表）。 */
export function formatPanel(
  values: Record<string, string>,
  keys: readonly string[],
): string {
  const lines: string[] = [];
  for (const key of keys) {
    const v = (values[key] ?? "").trim();
    if (v) lines.push(`${key} = ${v}`);
  }
  return lines.join("\n");
}

// ------------------------------------------------- 角色面板的自定义对外项（out::）
/** 子命名空间前缀（与后端 expr.SUB_OUT 一致） */
export const SUB_OUT = "out";

/** 自定义对外项名字的兜底规则（后端 schema 会给 panelCustomPattern，这里只兜底）。 */
export const DEFAULT_PANEL_CUSTOM_PATTERN = "^[a-z][a-z0-9_]*$";

/**
 * 自定义对外项的名字是否合法：正则（来自 schema）+ ``__`` 段。
 *
 * 为什么走 schema：名字规则的后端权威是 ``nodes.valid_panel_custom_name``，
 * 前端只是提前拦一下，不该在 TS 里另立一套规则。
 */
export function validCustomOut(
  name: string,
  pattern = DEFAULT_PANEL_CUSTOM_PATTERN,
): boolean {
  const t = (name ?? "").trim();
  if (!t || t.includes("__")) return false;
  try {
    return new RegExp(pattern).test(t);
  } catch {
    return new RegExp(DEFAULT_PANEL_CUSTOM_PATTERN).test(t);
  }
}

/** 列出一个自定义对外项的重复名（新增时给个 suggestion） */
export function nextCustomOutName(taken: readonly string[]): string {
  const used = new Set(taken);
  if (!used.has("buff")) return "buff";
  let i = 2;
  while (used.has(`buff${i}`)) i += 1;
  return `buff${i}`;
}

/** 面板文本里 ``out::名字`` 的自定义对外项（按出现顺序，已过滤非法名）。 */
export function parseCustomOuts(text: string, pattern?: string): string[] {
  const out: string[] = [];
  for (const [name] of panelLines(text)) {
    if (!name.startsWith(`${SUB_OUT}::`)) continue;
    const key = name.slice(SUB_OUT.length + 2).trim();
    if (!validCustomOut(key, pattern) || out.includes(key)) continue;
    out.push(key);
  }
  return out;
}

/** 解析角色卡「面板」字段：固定宏的值 + 自定义对外项（``out::名字``）的名字。 */
export function parseRolePanel(
  text: string,
  keys: readonly string[],
  pattern?: string,
): { values: Record<string, string>; custom: string[] } {
  const values: Record<string, string> = {};
  const custom: string[] = [];
  for (const [name, value] of panelLines(text)) {
    if (keys.includes(name)) {
      values[name] = value;
      continue;
    }
    if (!name.startsWith(`${SUB_OUT}::`)) continue;   // 其它名字（乱写的）忽略
    const key = name.slice(SUB_OUT.length + 2).trim();
    if (!validCustomOut(key, pattern)) continue;
    values[`${SUB_OUT}::${key}`] = value;
    if (!custom.includes(key)) custom.push(key);
  }
  return { values, custom };
}

/** 反向：固定宏按词表顺序写，自定义对外项按 `custom` 顺序写（``out::名字``）。 */
export function formatRolePanel(
  values: Record<string, string>,
  keys: readonly string[],
  custom: readonly string[] = [],
): string {
  const fixed = keys
    .map((key) => [key, (values[key] ?? "").trim()] as const)
    .filter(([, v]) => v)
    .map(([key, v]) => `${key} = ${v}`);
  const extra = custom
    .map((name) => [`${SUB_OUT}::${name}`, (values[`${SUB_OUT}::${name}`] ?? "").trim()] as const)
    .filter(([, v]) => v)
    .map(([key, v]) => `${key} = ${v}`);
  return [...fixed, ...extra].join("\n");
}

/**
 * 画布上那块「面板」显示哪些宏（空格 / 逗号 / 顿号分隔的宏名）。
 * 留空 = **只显示已有值的那些**（新角色不显示空面板）。
 */
export function parsePanelShow(text: string): string[] {
  return (text ?? "")
    .split(/[\s,，、]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * 「面板变量卡」的**预设代码**（拖进角色区域时由程序填进变量卡片的 `defs`）。
 *
 * 口径（用户确认）：面板属性**不自动计算**，全部由变量卡里的这些定义算出来；
 * 公式用 `own::`（自己写的）`+ in::`（收进来的拐）—— `out::` 是给出去的。
 * 宏名一律取自后端 schema 的 `panelMacros`，前端不硬编码。
 */
export function panelPreset(macros: readonly { key: string }[]): string {
  return macros.map((m) => `${m.key} = own::${m.key} + in::${m.key}`).join("\n");
}

/** 这张变量卡是不是"刚拖进角色区域、内容还空着"（该填预设代码） */
/**
 * 拖拽结束时的落位处理：变量卡**落进角色区域**且内容为空 → 填入面板预设代码。
 *
 * 返回新节点数组与"这次真正填了哪些 id"（调用方把 id 记下来，避免用户在清空后又反复被填）。
 * 纯函数，便于单测。
 */
export function fillPresetForDropped(
  nodes: CardNode[],
  ids: readonly string[],
  macros: readonly { key: string }[],
  filledIds: readonly string[] = [],
): { nodes: CardNode[]; filled: string[] } {
  const boxes = roleBoxes(nodes);
  const filled: string[] = [];
  const next = nodes.map((n) => {
    if (!ids.includes(n.id)) return n;
    const role = roleOfNode(n, boxes);
    if (!needsPanelPreset(n, role, filledIds.includes(n.id))) return n;
    filled.push(n.id);
    return { ...n, fields: { ...n.fields, defs: panelPreset(macros) } };
  });
  return { nodes: next, filled };
}

export function needsPanelPreset(
  node: { type: string; fields: Record<string, unknown> },
  role: string,
  alreadyFilled: boolean,
): boolean {
  if (alreadyFilled || node.type !== "var" || !role) return false;
  return String(node.fields.defs ?? "").trim() === "";
}

export function formatPanelShow(keys: readonly string[]): string {
  return keys.join(" ");
}

/** 生成不重复的节点 id：n1、n2… */
export function nextNodeId(nodes: CardNode[]): string {
  let max = 0;
  for (const n of nodes) {
    const m = /^n(\d+)$/.exec(n.id);
    if (m) max = Math.max(max, Number(m[1]));
  }
  return `n${max + 1}`;
}

/** 按 schema 造一张新卡片（字段取默认值，可覆盖）。
 *
 * ``siblings`` 是画布上已有的卡片：只有「角色」容器需要它来自动起一个不重名的默认名。
 */
export function makeNode(
  schema: Schema,
  type: string,
  pos: [number, number],
  id: string,
  overrides: Record<string, string> = {},
  siblings: CardNode[] = [],
): CardNode {
  const spec = schema.nodeTypes[type];
  if (!spec) throw new Error(`未知卡片类型: ${type}`);
  const fields: Fields = { ...spec.defaults };
  for (const [k, v] of Object.entries(overrides)) {
    if (k in fields) fields[k] = v;
  }
  const isRole = type === "role";
  if (isRole && !fields.role_name) {
    // 抽象角色的名字完全自定义，默认按 角色N 起一个不容易重名的
    fields.role_name = nextRoleName(siblings);
  }
  return {
    id,
    type,
    pos,
    // 容器要立刻够大（否则新建出来是个小卡片，拖不进东西）
    size: isRole ? [ROLE_W, ROLE_H] : null,
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
    // 端口号必须落在目标卡片真实的输入端口范围内（旧存档里多余的端口会被丢弃）；
    // **角色卡例外**：它没有伤害端口，但「拐力箭头」（角色→角色）走 port 0，
    // 不能按 inputs=0 被丢掉。
    const target = byId.get(dst);
    const srcNode = byId.get(src);
    const isBuff = Boolean(target && srcNode && target.type === "role" && srcNode.type === "role");
    const maxPort = isBuff ? 1 : (target ? target.inputs : 0);
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
