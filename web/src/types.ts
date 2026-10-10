/**
 * 与后端 `/api/schema`、`/api/evaluate` 对应的类型定义。
 *
 * 关键约定：**前端不做伤害计算**，卡片长什么样、有哪些字段全部由后端 schema 驱动，
 * 计算结果（系数 / 未暴击 / 暴击 / 期望）也全部来自后端。
 */

export type FieldKind = "num" | "pct" | "combo" | "check" | "text" | "textbox";

export interface FieldSpec {
  key: string;
  label: string;
  default: string | number | boolean;
  kind: FieldKind;
  options?: string[];
}

export interface NodeTypeSpec {
  type: string;
  title: string;
  label: string;
  group: string;
  /** 输入端口数（固定值，由后端 schema 决定） */
  inputs: number;
  fields: FieldSpec[];
  defaults: Record<string, string | number | boolean>;
  isolated: boolean;
  no_output: boolean;
  resizable: boolean;
  wide_fields: boolean;
  /** 便签式卡片：不画字段标签、输入框不带边框与内边距（见 genshin_dmg/nodes.py 的 text 卡） */
  bare: boolean;
  plain: boolean;
  copyable: boolean;
  font_menu: boolean;
  vars_card: boolean;
  ctx_menu: boolean;
  has_factor: boolean;
  /** 纯汇点卡片（有输入端口、没有输出端口，如「赋值变量」）：不参与结果链 */
  sink: boolean;
  table: string | null;
  hidden_fields: string[];
}

export interface PaletteItem {
  type: string;
  label: string;
}

export interface PaletteGroup {
  name: string;
  items: PaletteItem[];
}

export interface PresetItem {
  type: string;
  fields: Record<string, string>;
}

export interface TableSpec {
  header: string[];
  rows?: string[][];
}

export interface Schema {
  version: number;
  app: string;
  groups: PaletteGroup[];
  nodeTypes: Record<string, NodeTypeSpec>;
  presets: Record<string, PresetItem[]>;
  tables: Record<string, TableSpec>;
  resultVarFields: { key: string; label: string }[];
  zoom: { min: number; max: number; step: number };
  history: { max: number };
}

/** 卡片字段的原始值：数值框保持字符串，只有勾选框是布尔。 */
export type FieldValue = string | number | boolean;
export type Fields = Record<string, FieldValue>;

/** 画布上的一个节点（与工程 JSON 的 nodes[] 一致）。 */
export interface GraphNodeJSON {
  id: string;
  type: string;
  pos: [number, number];
  size: [number, number] | null;
  font_size: number | null;
  inputs: number;
  fields: Fields;
  /**
   * 卡片是否折叠（只显示卡片类型）。
   *
   * 属于**界面状态**：会写进工程 JSON / localStorage，但**不进 `/api/evaluate` 载荷**
   * （折叠不影响计算，见 App.tsx 的 evalPayload）。
   */
  collapsed?: boolean;
}

export interface GraphLinkJSON {
  src: string;
  dst: string;
  port: number;
}

export interface GraphJSON {
  version: number;
  app: string;
  zoom: number;
  name: string;
  nodes: GraphNodeJSON[];
  links: GraphLinkJSON[];
}

export interface Triple {
  noncrit: number;
  crit: number;
  expected: number;
}

export interface NodeResult {
  type: string;
  title: string;
  factor: string | null;
  values: Triple | null;
  isTriple: boolean;
  display: string;
  error: string | null;
  rows: string[][] | null;
  varsText: string | null;
  boundNames: string[];
  /** 未暴击值的纯数字字符串（复制用） */
  plain: string;
  plainTriple: string[];
}

export interface VariableEntry {
  name: string;
  value: number;
  text: string;
}

export interface EvaluateResult {
  ok: boolean;
  error: string | null;
  result: {
    nodeId: string;
    values: Triple;
    display: string;
    boundNames: string[];
  } | null;
  variables: VariableEntry[];
  nodes: Record<string, NodeResult>;
  chainTypes: string[];
  warnings: string[];
  graph?: GraphJSON;
}

/** 画布节点：工程 JSON 的字段 + 若干**仅供界面使用**的字段（不入 JSON）。 */
export interface CardNode extends GraphNodeJSON {
  /** React Flow 的选中态 */
  selected?: boolean;
  /** React Flow 实测尺寸（用于落位/对齐；用户拖动 ◢ 后以 size 为准） */
  measured?: { width: number; height: number };
  /** 正在拖动改变大小（此时不覆盖 React Flow 的内部尺寸） */
  resizing?: boolean;
}
