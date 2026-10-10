/**
 * 卡片内嵌的只读表格（理想圣遗物词条 / 变量表共用）。
 *
 * 交互与旧版一致：点单元格选中（蓝色高亮），按住拖动选一块矩形，
 * 选中后 Ctrl+C 复制（单格原文；多格/多行 TSV，可直接粘进 Excel）；未选中时复制整表。
 */
import { useCallback, useRef, useState, type KeyboardEvent } from "react";
import { copyText } from "../clipboard";

export interface DataTableProps {
  header: string[];
  rows: string[][];
  /** 变量表用等宽字体更整齐 */
  mono?: boolean;
  testId?: string;
}

export interface Cell {
  r: number;
  c: number;
}

/** 选中区域 → 可粘贴文本（TSV）。未选中时给整表（含表头）。 */
export function selectionText(
  header: string[],
  rows: string[][],
  sel: { a: Cell; b: Cell } | null,
): string {
  if (!sel) {
    return [header, ...rows].map((r) => r.join("\t")).join("\n");
  }
  const r1 = Math.min(sel.a.r, sel.b.r);
  const r2 = Math.max(sel.a.r, sel.b.r);
  const c1 = Math.min(sel.a.c, sel.b.c);
  const c2 = Math.max(sel.a.c, sel.b.c);
  if (r1 === r2 && c1 === c2) {
    const row = rows[r1];
    return row && row[c1] !== undefined ? String(row[c1]) : "";
  }
  const out: string[] = [];
  for (let r = r1; r <= r2; r += 1) {
    const row = rows[r] ?? [];
    const cells: string[] = [];
    for (let c = c1; c <= c2; c += 1) cells.push(row[c] ?? "");
    out.push(cells.join("\t"));
  }
  return out.join("\n");
}

export default function DataTable({ header, rows, mono, testId }: DataTableProps) {
  const [sel, setSel] = useState<{ a: Cell; b: Cell } | null>(null);
  const dragging = useRef(false);
  const boxRef = useRef<HTMLDivElement>(null);

  const inRange = useCallback(
    (r: number, c: number) => {
      if (!sel) return false;
      return (
        r >= Math.min(sel.a.r, sel.b.r) &&
        r <= Math.max(sel.a.r, sel.b.r) &&
        c >= Math.min(sel.a.c, sel.b.c) &&
        c <= Math.max(sel.a.c, sel.b.c)
      );
    },
    [sel],
  );

  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c") {
        e.preventDefault();
        e.stopPropagation();
        void copyText(selectionText(header, rows, sel));
      }
    },
    [header, rows, sel],
  );

  const cols = Math.max(1, header.length);
  // 整表一套列宽（CSS Grid）——如果让每行各自 flex，各行会按自己的内容算宽度，
  // 同一列在上下行就会对不齐（这是之前的 bug）。行盒子用 display:contents，
  // 单元格直接参与同一个网格，列宽自然一致。
  const gridStyle = {
    gridTemplateColumns: `repeat(${cols}, minmax(${mono ? 78 : 62}px, 1fr))`,
  };

  return (
    <div
      ref={boxRef}
      className={`dtable${mono ? " dtable-mono" : ""}`}
      style={gridStyle}
      tabIndex={0}
      role="grid"
      data-testid={testId}
      onKeyDown={onKeyDown}
      onMouseDown={() => {
        dragging.current = true;
        boxRef.current?.focus();
      }}
      onMouseUp={() => {
        dragging.current = false;
      }}
      onMouseLeave={() => {
        dragging.current = false;
      }}
      title="点单元格选中；拖动可选一块区域；Ctrl+C 复制（未选中时复制整表）"
    >
      <div className="dtable-row dtable-head" role="row">
        {header.map((h) => (
          <div key={h} className="dtable-cell dtable-th" role="columnheader">
            {h}
          </div>
        ))}
      </div>
      {rows.map((row, r) => (
        <div className="dtable-row" role="row" key={`r${r}`}>
          {row.map((cellValue, c) => (
            <div
              key={`c${r}-${c}`}
              role="gridcell"
              className={`dtable-cell${inRange(r, c) ? " dtable-sel" : ""}`}
              onMouseDown={(e) => {
                e.stopPropagation();
                dragging.current = true;
                setSel({ a: { r, c }, b: { r, c } });
                boxRef.current?.focus();
              }}
              onMouseEnter={() => {
                if (dragging.current) setSel((s) => (s ? { a: s.a, b: { r, c } } : s));
              }}
            >
              {cellValue}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
