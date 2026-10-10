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
  const hasOutput = !spec.isolated && !spec.no_output;
  /** 折叠状态：只显示卡片类型（标题栏），字段区与底部输出都收起 */
  const collapsed = Boolean(node.collapsed);

  const onField = useCallback(
    (key: string, v: FieldValue) => data.onField(id, key, v),
    [data, id],
  );

  const title = collapsed
    ? spec.label
    : node.type === "calc"
      ? String(node.fields.title ?? spec.title) || spec.title
      : spec.title;

  const body = collapsed ? null : (
    <div className={`card-body${spec.bare ? " card-body-bare" : ""}`}>
      {spec.table && table ? (
        <DataTable
          header={table.header}
          rows={table.rows}
          mono={spec.table === "vars"}
          testId={`table-${spec.table}-${id}`}
        />
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
        className={`card${selected ? " card-sel" : ""}${node.type === "result" ? " card-result" : ""}${collapsed ? " card-collapsed" : ""}`}
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
