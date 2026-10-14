/**
 * 画布上的一张卡片。
 *
 * 卡片长什么样完全由后端 schema 驱动：字段控件按 `kind` 渲染，
 * 结果文案（本卡系数 ｜ 输出）直接用后端返回的 `display`，保证与 Python 侧完全一致。
 */
import { Handle, NodeResizer, Position, type Node, type NodeProps } from "@xyflow/react";
import { memo, useCallback } from "react";
import type { CardNode, FieldSpec, FieldValue, NodeResult, NodeTypeSpec } from "../types";
import DataTable from "./DataTable";

export interface CardData extends Record<string, unknown> {
  node: CardNode;
  spec: NodeTypeSpec;
  result: NodeResult | null;
  fontSize: number;
  /** 表格类卡片的内容（const 静态 / vartable 动态） */
  table: { header: string[]; rows: string[][] } | null;
  /** 这张卡片属于哪个「角色」命名空间（由画布上的容器面板按位置推导，空 = 不属于任何角色） */
  role: string;
  /** 角色容器面板里当前有几张卡片（只对 role_card 有意义） */
  roleCount?: number;
  onField: (id: string, key: string, value: FieldValue) => void;
  onDelete: (id: string) => void;
  /** 拖动缩放手柄结束后把最终尺寸（含左上角坐标变化）写回模型 */
  onResize: (id: string, size: [number, number], pos: [number, number]) => void;
  onMenu: (id: string, kind: MenuKind, ev: { clientX: number; clientY: number }) => void;
  onCopy: (id: string) => void;
}

export type MenuKind = "result" | "font" | "card";
export type CardRFNode = Node<CardData, "card">;

function FieldControl({
  field,
  value,
  onChange,
  bare = false,
}: {
  field: FieldSpec;
  value: FieldValue;
  onChange: (v: FieldValue) => void;
  /** 便签式卡片：不画标签、控件不带边框（由 schema 的 bare 字段决定） */
  bare?: boolean;
}) {
  const label = bare ? null : <span className="f-label">{field.label}</span>;
  switch (field.kind) {
    case "check":
      return (
        <label className="f-check">
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
          />
          <span>{field.label}</span>
        </label>
      );
    case "combo": {
      const options = field.options ?? [];
      const current = String(value ?? "");
      const list = options.includes(current) || !current ? options : [current, ...options];
      return (
        <>
          {label}
          <select
            className="f-input"
            value={current}
            onChange={(e) => onChange(e.target.value)}
            title={current}
          >
            {list.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </>
      );
    }
    case "textbox":
      return (
        <>
          {label}
          <textarea
            className={`f-input f-area${bare ? " f-bare" : ""}`}
            value={String(value ?? "")}
            rows={bare ? undefined : field.key === "content" ? 4 : 3}
            spellCheck={false}
            onChange={(e) => onChange(e.target.value)}
          />
        </>
      );
    case "pct":
      return (
        <>
          <span className="f-label">{field.label}</span>
          <span className="f-wrap">
            <input
              className="f-input"
              value={String(value ?? "")}
              spellCheck={false}
              onChange={(e) => onChange(e.target.value)}
            />
            <span className="f-suffix">%</span>
          </span>
        </>
      );
    default:
      return (
        <>
          <span className="f-label">{field.label}</span>
          <input
            className="f-input"
            value={String(value ?? "")}
            spellCheck={false}
            onChange={(e) => onChange(e.target.value)}
          />
        </>
      );
  }
}

function CardNodeView({ id, data, selected }: NodeProps<CardRFNode>) {
  const { node, spec, result, fontSize, table } = data;
  const hasInput = !spec.isolated && spec.inputs > 0;
  // sink 卡片（「赋值变量」）只有输入端口：它不参与结果链，只把上游值记到变量表
  const hasOutput = !spec.isolated && !spec.no_output && !spec.sink;
  /** 折叠状态：只显示卡片类型（标题栏），字段区与底部输出都收起 */
  const collapsed = Boolean(node.collapsed);

  const onField = useCallback(
    (key: string, v: FieldValue) => data.onField(id, key, v),
    [data, id],
  );

  // 标题栏文案：
  //  * 角色容器 → 「角色 · 自定义角色名」
  //  * 计算卡 → 它自己的标题（历史行为）
  //  * 其余 → 卡片类型（命名后的名字另挂徽标，见下面的 card-name-chip）
  const cardName = String(node.fields.card_name ?? "").trim();
  const baseTitle =
    node.type === "calc" ? String(node.fields.title ?? spec.title) || spec.title : spec.title;
  const title = collapsed
    ? spec.label
    : node.type === "role"
      ? `角色 · ${String(node.fields.role_name ?? "").trim() || "未命名"}`
      : baseTitle;

  const body = collapsed ? null : (
    <div
      className={`card-body${spec.bare ? " card-body-bare" : ""}${
        spec.table ? " card-body-table" : ""
      }`}
    >
      {spec.table && table ? (
        <DataTable
          header={table.header}
          rows={table.rows}
          mono={spec.table === "vars"}
          testId={`table-${spec.table}-${id}`}
        />
      ) : null}
      {spec.role_card ? (
        // 角色容器只是**背景标记**：区域不吃鼠标（见 App.tsx 的内联 pointer-events），
        // 这里只留一句说明 + 可编辑的角色名，看上去就不像一张"卡片"
        <p className="role-hint">
          这是背景标记：把卡片拖进这块区域就算属于角色「
          {String(node.fields.role_name ?? "").trim() || "未命名"}」，
          里面的变量按 <b>{String(node.fields.role_name ?? "").trim() || "角色名"}::变量名</b>{" "}
          加入命名空间（本角色内可直接写变量名）。当前 {data.roleCount ?? 0} 张卡片。
        </p>
      ) : null}
      {spec.fields.map((f) => (
        <div className={`f-row${spec.bare ? " f-row-bare" : ""}`} key={f.key}>
          <FieldControl
            field={f}
            value={node.fields[f.key]}
            onChange={(v) => onField(f.key, v)}
            bare={spec.bare}
          />
        </div>
      ))}
    </div>
  );

  const footer = collapsed ? null : (() => {
    if (spec.no_output) return null;
    if (node.type === "var") {
      return (
        <div className="card-foot">
          {result?.varsText ? <span className="foot-text">{result.varsText}</span> : null}
        </div>
      );
    }
    if (!result) {
      return (
        <div className="card-foot">
          <span className="foot-dim">计算中…</span>
        </div>
      );
    }
    if (result.error) {
      return (
        <div className="card-foot foot-error">
          <span>输出: 错误({result.error})</span>
        </div>
      );
    }
    return (
      <div className={`card-foot${node.type === "result" ? " foot-result" : ""}`}>
        <span className="foot-text">{result.display || "—"}</span>
        {spec.copyable ? (
          <button
            type="button"
            className="foot-copy"
            title="复制输出数值"
            onClick={() => data.onCopy(id)}
          >
            复制
          </button>
        ) : null}
      </div>
    );
  })();

  const handles = [];
  if (hasInput) {
    const n = Math.max(1, node.inputs);
    for (let i = 0; i < n; i += 1) {
      handles.push(
        <Handle
          key={`in-${i}`}
          id={`in-${i}`}
          type="target"
          position={Position.Left}
          style={{ top: `${((i + 1) / (n + 1)) * 100}%` }}
          className="port port-in"
        />,
      );
    }
  }
  if (hasOutput && !spec.no_output) {
    handles.push(
      <Handle
        key="out"
        id="out"
        type="source"
        position={Position.Right}
        className="port port-out"
      />,
    );
  }

  return (
    <>
      <NodeResizer
        isVisible={Boolean(selected) && !collapsed}
        minWidth={160}
        minHeight={90}
        lineClassName="resize-line"
        handleClassName="resize-handle"
        onResizeEnd={(_event, params) => {
          // 显式把最终尺寸写回模型：否则卡片高度只存在于 React Flow 内部，
          // 下一次重渲染会用旧尺寸覆盖回去，表现为「纵向缩放不动」。
          data.onResize(
            id,
            [Math.round(params.width), Math.round(params.height)],
            [Math.round(params.x), Math.round(params.y)],
          );
        }}
      />
      <div
        className={`card${selected ? " card-sel" : ""}${node.type === "result" ? " card-result" : ""}${collapsed ? " card-collapsed" : ""}${spec.role_card ? " card-role-box" : ""}`}
        style={fontSize ? { fontSize: `${fontSize}px` } : undefined}
        data-testid={`card-${id}`}
        data-type={node.type}
        data-collapsed={collapsed ? "1" : undefined}
      >
        <div
          className="card-head"
          onContextMenu={(e) => {
            e.preventDefault();
            const kind: MenuKind = spec.ctx_menu
              ? "result"
              : spec.font_menu
                ? "font"
                : "card";
            data.onMenu(id, kind, { clientX: e.clientX, clientY: e.clientY });
          }}
        >
          <span className="card-title" title={spec.title}>
            {title}
          </span>
          {/* 命名空间徽标：只显示**名字本身**，不带尾随 `::`
              —— `::` 后面没有字段时没必要显示（用户要求）；完整用法写在 title 里 */}
          {cardName && !collapsed && node.type !== "calc" ? (
            <span
              className="card-name-chip"
              title={`引用这张卡的输出：${cardName}（期望值）／ ${cardName}::暴击 ／ ${cardName}::未暴击`}
            >
              {cardName}
            </span>
          ) : null}
          {data.role && !collapsed ? (
            <span
              className="card-role-chip"
              title={`属于角色「${data.role}」：其中的变量写作 ${data.role}::变量名`}
            >
              {data.role}
            </span>
          ) : null}
          <button
            type="button"
            className="card-x nodrag"
            title="删除卡片"
            onClick={() => data.onDelete(id)}
          >
            ✕
          </button>
        </div>
        {body}
        {footer}
      </div>
      {handles}
    </>
  );
}

export default memo(CardNodeView);
