/**
 * 「域对照表」某个单元格的角色面板（右键单元格打开）。
 *
 * 样式与「角色面板」弹窗**完全一致**（用户要求）：直接复用 PanelParts 里的宏表 /
 * 拐力列表，外壳也用同一个 `modal modal-role-panel`。
 * 区别只是只读：值来自"汇总了该行 + 该列 + 全局拐力之后"的求值结果。
 */
import type { CellPanel } from "../api";
import { BuffRows, PanelMacroGrid } from "./PanelParts";

export interface MatrixPanelDialogProps {
  data: CellPanel;
  onClose: () => void;
}

export default function MatrixPanelDialog({ data, onClose }: MatrixPanelDialogProps) {
  const rows = data.rows ?? [];
  const values = Object.fromEntries(rows.map((r) => [r.key, r.value]));
  const incoming = Object.fromEntries(rows.map((r) => [r.key, r.incoming]));
  const macros = rows.map((r) => ({ key: r.key, label: r.label }));

  return (
    <div className="modal-mask" onMouseDown={onClose}>
      <div
        className="modal modal-role-panel"
        role="dialog"
        aria-label="角色面板"
        data-testid="matrix-cell-panel"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2>角色面板 · {data.title ?? "—"}</h2>
        <PanelMacroGrid
          macros={macros}
          values={values}
          incoming={incoming}
          readOnly
          testIdPrefix="cell-panel"
        />
        <div className="buff-stats">
          <div>
            <h3>给出去的拐（OUT）</h3>
            <BuffRows list={data.out ?? []} emptyTestId="cell-panel-out-empty" />
          </div>
          <div>
            <h3>收到的拐（IN）</h3>
            <BuffRows
              list={rows
                .filter((r) => r.incoming)
                .map((r) => ({ macro: r.key, label: r.label, value: r.incoming }))}
              emptyTestId="cell-panel-in-empty"
            />
          </div>
        </div>
        <div className="modal-actions">
          <span className="grow" />
          <button type="button" onClick={onClose}>
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
