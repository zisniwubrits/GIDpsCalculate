/**
 * 「域对照表」的表格编辑器。
 *
 * 用户要求：行 / 列 / 固定拐力**不要**放在卡片底部当普通字段，直接在表格里选。
 * 所以这张表自己就是编辑器：
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
import { useEffect, useRef, useState } from "react";
import {
  insertSourceLine,
  removeSourceLine,
  setSourceLine,
  sourceLines,
} from "../model";
import ExternalSources from "./ExternalSources";

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
  disabled?: boolean;
  baseDir?: string;
  onRows: (next: string) => void;
  onCols: (next: string) => void;
  onFixed: (next: string) => void;
}

type Axis = "row" | "col";

export default function MatrixEditor({
  id,
  rows,
  cols,
  fixed,
  table,
  disabled,
  baseDir,
  onRows,
  onCols,
  onFixed,
}: MatrixEditorProps) {
  const rowLines = sourceLines(rows);
  const colLines = sourceLines(cols);
  const header = table?.[0] ?? [];
  const body = table?.slice(1) ?? [];

  /** 行 / 列各自那串输入框；回车加一条后要把光标搬到新那条上 */
  const boxes = {
    row: useRef<Array<HTMLInputElement | null>>([]),
    col: useRef<Array<HTMLInputElement | null>>([]),
  };
  const [focusAt, setFocusAt] = useState<{ axis: Axis; index: number } | null>(null);

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
    return (
      <input
        key={index}
        ref={(el) => {
          boxes[axis].current[index] = el;
        }}
        className="f-input mx-input"
        data-testid={`mx-${axis}-${id}-${index}`}
        value={lines[index] ?? ""}
        disabled={disabled}
        spellCheck={false}
        title={header[index + 1] ?? undefined}
        onChange={(e) => onChange(setSourceLine(value, index, e.target.value))}
        onKeyDown={(e) => {
          if (e.nativeEvent.isComposing) return;
          if (e.key === "Enter") {
            e.preventDefault();
            onChange(insertSourceLine(value, index));
            setFocusAt({ axis, index: index + 1 });   // 光标跟到新加的那条
            return;
          }
          if (e.key === "Backspace" && (lines[index] ?? "") === "" && lines.length > 1) {
            e.preventDefault();
            onChange(removeSourceLine(value, index));
            setFocusAt({ axis, index: Math.max(0, index - 1) });
          }
        }}
      />
    );
  };

  return (
    <table className="mx-table" data-testid={`matrix-${id}`}>
      <thead>
        <tr>
          <th className="mx-corner">
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
            <th key={index} className="mx-col">
              {renderInput("col", index)}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rowLines.map((_line, index) => (
          <tr key={index}>
            <th className="mx-row">{renderInput("row", index)}</th>
            {colLines.map((_c, ci) => (
              <td key={ci} className="mx-cell">
                {body[index]?.[ci + 1] ?? "—"}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
