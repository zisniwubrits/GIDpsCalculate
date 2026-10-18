/**
 * 「域对照表」的表格编辑器。
 *
 * 用户要求：行 / 列 / 固定拐力**不要**放在卡片底部当普通字段，直接在表格里选；
 * 补全用小弹窗（SourceInput）。
 *
 *   ┌─────────────┬──────────┬──────────┐
 *   │ 固定拐力列表 │  列1输入 │  列2输入 │   ← 表头行：左上角是固定拐力（可多选）
 *   ├─────────────┼──────────┼──────────┤
 *   │ 行1输入      │ 期望伤害 │ 期望伤害 │   ← 左侧纵列：每行一个文件
 *   └─────────────┴──────────┴──────────┘
 *
 * 增删逻辑与「外部域」一致（回车在**后面**加一条并把光标移过去、空行按退格删掉、
 * 永远留一条）；两边共用 model 里的 sourceLines / setSourceLine / insertSourceLine /
 * removeSourceLine，行为不会出现两套。
 */
import { Handle, Position, useUpdateNodeInternals } from "@xyflow/react";
import { useEffect, useRef, useState } from "react";
import {
  MATRIX_PORT_ALL,
  displayWidthCh,
  insertSourceLine,
  matrixColPort,
  matrixRowPort,
  removeSourceLine,
  setSourceLine,
  sourceLines,
} from "../model";
import ExternalSources from "./ExternalSources";
import SourceInput from "./SourceInput";

export interface MatrixEditorProps {
  id: string;
  /** 行来源（换行分隔，每行一个文件） */
  rows: unknown;
  /** 列来源 */
  cols: unknown;
  /** 固定拐力（换行分隔，可多条） */
  fixed: unknown;
  /** 后端返回的整表：第一行表头（角标 + 列名），其余每行 [行名, 格…] */
  table: string[][] | null;
  /** 每格相对基准单元格的百分比（与 table 同形，null = 没设基准 / 读不到） */
  ratios?: (number | null)[][] | null;
  /** 基准单元格 "行,列"（行列都不含表头） */
  baseCell: unknown;
  disabled?: boolean;
  baseDir?: string;
  onRows: (next: string) => void;
  onCols: (next: string) => void;
  onFixed: (next: string) => void;
  /** 双击单元格 → 把它设成百分比基准 */
  onBase: (next: string) => void;
  /** 右键数据格 → 看这个单元格的角色面板（汇总了行列拐力之后） */
  onCellPanel: (row: number, col: number) => void;
}

type Axis = "row" | "col";

export default function MatrixEditor({
  id,
  rows,
  cols,
  fixed,
  table,
  ratios,
  baseCell,
  disabled,
  baseDir,
  onRows,
  onCols,
  onFixed,
  onBase,
  onCellPanel,
}: MatrixEditorProps) {
  const rowLines = sourceLines(rows);
  const colLines = sourceLines(cols);
  const header = table?.[0] ?? [];
  const body = table?.slice(1) ?? [];
  // 条形宽度按"本表最大的那个百分比"归一（基准不一定最大 —— 有格子超过基准时也对）
  let maxPct = 0;
  for (const line of ratios ?? []) {
    for (const pct of line ?? []) {
      if (typeof pct === "number" && pct > maxPct) maxPct = pct;
    }
  }
  if (maxPct <= 0) maxPct = 100;
  // 行头这一列要多宽：取最长的那条路径（全角按 2 计），夹在 16~48 字符之间
  let rowColCh = 16;
  for (const line of rowLines) {
    rowColCh = Math.max(rowColCh, Math.round(displayWidthCh(line)) + 3);
  }
  rowColCh = Math.min(48, rowColCh);

  /** 行 / 列各自那串输入框；回车加一条后要把光标搬到新那条上 */
  const boxes = {
    row: useRef<Array<HTMLInputElement | null>>([]),
    col: useRef<Array<HTMLInputElement | null>>([]),
  };
  const [focusAt, setFocusAt] = useState<{ axis: Axis; index: number } | null>(null);
  const updateNodeInternals = useUpdateNodeInternals();

  // 行 / 列数量变了，接入点的位置也变了：必须让 React Flow 重新测量，
  // 否则「增删行之后输入点还在老位置」——连线会指到错误的地方（用户报的 bug）
  useEffect(() => {
    updateNodeInternals(id);
  }, [id, rowLines.length, colLines.length, updateNodeInternals]);

  // 光标只搬一次，而且**等新那条渲染出来**再搬（等不到就留着，下次渲染再来）
  useEffect(() => {
    if (!focusAt) return;
    const el = boxes[focusAt.axis].current[focusAt.index];
    if (!el) return;
    el.focus();
    const end = el.value.length;
    el.setSelectionRange(end, end);
    setFocusAt(null);
  }, [focusAt, rowLines.length, colLines.length]);

  const renderInput = (axis: Axis, index: number) => {
    const lines = axis === "row" ? rowLines : colLines;
    const value = axis === "row" ? rows : cols;
    const onChange = axis === "row" ? onRows : onCols;
    const text = lines[index] ?? "";
    // 文件名可能很长：让输入框按内容给出固有宽度（size 以"字符"计），
    // 列宽就会跟着内容变，不会把路径截断（用户要求：行头要能显示全）
    const widthCh = Math.max(10, Math.min(48, Math.round(displayWidthCh(text)) + 2));
    return (
      <SourceInput
        key={index}
        value={text}
        disabled={disabled}
        baseDir={baseDir}
        className="mx-input"
        testId={`mx-${axis}-${id}-${index}`}
        size={widthCh}
        inputRef={(el) => {
          boxes[axis].current[index] = el;
        }}
        onChange={(next) => onChange(setSourceLine(value, index, next))}
        onEnter={() => {
          onChange(insertSourceLine(value, index));
          setFocusAt({ axis, index: index + 1 });   // 光标跟到新加的那条
        }}
        onEmptyBackspace={() => {
          if (lines.length <= 1) return;
          onChange(removeSourceLine(value, index));
          setFocusAt({ axis, index: Math.max(0, index - 1) });
        }}
      />
    );
  };

  return (
    <table className="mx-table" data-testid={`matrix-${id}`}>
      {/* 列宽：行头那列按最长路径给宽度，数据列**平分**剩下的宽度 ——
          否则 auto 布局会把多出来的空间塞给某一列，看起来列宽忽宽忽窄 */}
      <colgroup>
        <col style={{ width: `${rowColCh}ch` }} />
        {colLines.map((_c, index) => (
          <col key={index} />
        ))}
      </colgroup>
      <thead>
        <tr>
          <th className="mx-corner">
            {/* 左上角接入点：拖到这里对所有行 × 列都加（全局固定拐力） */}
            <Handle
              id={`in-${MATRIX_PORT_ALL}`}
              type="target"
              position={Position.Left}
              className="port port-in mx-port mx-port-all"
            />
            {/* 左上角：固定拐力（可多选，增删与「外部域」同一套） */}
            <ExternalSources
              id={`${id}-fixed`}
              value={fixed}
              disabled={disabled}
              baseDir={baseDir}
              onChange={onFixed}
            />
          </th>
          {colLines.map((_line, index) => (
            <th key={index} className="mx-col" title={header[index + 1] ?? undefined}>
              {/* 列接入点：拖到这里只作用于**这一列** */}
              <Handle
                id={`in-${matrixColPort(index)}`}
                type="target"
                position={Position.Top}
                className="port port-in mx-port mx-port-col"
              />
              {renderInput("col", index)}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rowLines.map((_line, index) => (
          <tr key={index}>
            <th className="mx-row">
              {/* 行接入点：拖到这里只作用于**这一行** */}
              <Handle
                id={`in-${matrixRowPort(index)}`}
                type="target"
                position={Position.Left}
                className="port port-in mx-port mx-port-row"
              />
              {renderInput("row", index)}
            </th>
            {colLines.map((_c, ci) => {
              const pct = ratios?.[index]?.[ci] ?? null;
              const isBase =
                String(baseCell ?? "") === `${index},${ci}`;
              // 条形按"本表最大百分比"归一，100% 的基准格永远占满一半以上，
              // 这样一眼能看出各格的相对高低
              return (
                <td
                  key={ci}
                  className={`mx-cell${isBase ? " mx-base" : ""}`}
                  title={
                    pct === null
                      ? "双击设为百分比基准"
                      : `${pct.toFixed(2)}%${isBase ? "（基准）" : ""}\n双击设为基准`
                  }
                  onDoubleClick={() => onBase(`${index},${ci}`)}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    onCellPanel(index, ci);
                  }}
                >
                  <span className="mx-cell-value">{body[index]?.[ci + 1] ?? "—"}</span>
                  {pct === null ? null : (
                    <span className="mx-pct">
                      <span className="mx-track">
                        <span
                          className="mx-bar"
                          style={{ width: `${Math.min(100, pct / maxPct * 100)}%` }}
                        />
                      </span>
                      {/* 数字放在条下面（用户要求）：不会再压在深色条上看不清 */}
                      <span className="mx-pct-text">{pct.toFixed(1)}%</span>
                    </span>
                  )}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
