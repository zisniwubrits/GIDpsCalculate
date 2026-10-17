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
  /** 便签式卡片：不画字段标签、输入框不带边框并随卡片铺满（见 genshin_dmg/nodes.py 的 text / var 卡） */
  bare: boolean;
  plain: boolean;
  copyable: boolean;
  font_menu: boolean;
  vars_card: boolean;
  /** 「角色」容器面板（按位置给卡片划分命名空间） */
  role_card: boolean;
  /** 武器：继承角色类的命名空间容器，只输出拐力、无面板、不支持 in:: */
  weapon_card: boolean;
  /** 「外部域」：读另一个工程文件里某个域的 out:: 当拐力来源（不是命名空间容器） */
  external_domain: boolean;
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
  /** 「角色面板」的固定宏词表（前端不硬编码中文标签） */
  panelMacros: { key: string; label: string; feed: string }[];
  /**
   * 自定义面板项（`out::名字`）的命名规则（正则源码）。
   *
   * 规则的后端权威是 `nodes.valid_panel_custom_name`，前端只拿它做输入校验
   * （不在 TS 里另立一套规则）；后端版本过旧时可能没有这个字段。
   */
  panelCustomPattern?: string;
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
  /**
   * 这张卡片属于哪个「角色」命名空间（由画布上角色容器面板的位置推导）。
   *
   * **只在 `/api/evaluate` 载荷里出现**，不进工程 JSON —— 归属随时可由位置重算，
   * 存起来反而会跟画布不一致。后端据此做变量作用域的就近解析。
   */
  role?: string;
}

export interface GraphLinkJSON {
  src: string;
  dst: string;
  port: number;
}

/** 「角色面板」弹窗里的一行拐力统计（后端 buffStats 给的数据） */
export interface BuffStatRow {
  macro: string;
  label: string;
  value: number;
  /** OUT 行里是目标角色，IN 行里是来源角色 */
  role: string;
}

export interface GraphJSON {
  version: number;
  app: string;
  zoom: number;
  name: string;
  nodes: GraphNodeJSON[];
  links: GraphLinkJSON[];
  /**
   * 当前工程所在目录：后端解析「外部域」卡片的**相对路径**用的基准
   * （填 `dds.json` / `dds` 就指这个目录下的文件）。只随求值载荷发送，不落盘。
   */
  dir?: string;
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
  /** 「外部域」卡片：指向的工程文件里有哪些域（只有一个时前端藏掉「里面的域」那一栏） */
  extDomains?: string[];
  /** 哪些字段是"留空 → 用角色面板兜底"的（卡片上标「含面板」） */
  panelFields?: string[];
  /** 本角色是否收了别的角色的拐（卡片上标「含拐」） */
  buffed?: boolean;
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
  /** 拐力统计：{角色: {out: 给出去的, in: 收进来的}}（「角色面板」弹窗用） */
  buffStats?: Record<string, { out: BuffStatRow[]; in: BuffStatRow[] }>;
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
  /**
   * 拖动这个角色区域时**压到了别的区域**（临时高亮成红框）。
   *
   * 纯界面状态：只在拖动的那么一会儿为真，不入工程 JSON、不进求值载荷。
   * 为什么要它：区域框（560×380）比看得见的内容大十几倍，"压上了"在画面上
   * 根本看不出来，用户只会觉得"没碰撞还说不合法"。
   */
  colliding?: boolean;
}
