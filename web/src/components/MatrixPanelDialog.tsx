/**
 * 「域对照表」某个单元格的角色面板（右键单元格打开）。
 *
 * 显示的是**汇总了该行 / 该列 / 全局拐力之后**的面板：每项宏的生效值 + 收到的拐，
 * 下面再列它给出去的拐。只读（要改面板请去那个域自己的文件里改）。
 */
import type { CellPanel } from "../api";

export interface MatrixPanelDialogProps {
  data: CellPanel;
  onClose: () => void;
}

export default function MatrixPanelDialog({ data, onClose }: MatrixPanelDialogProps) {
  return (
    <div className="modal-mask" onMouseDown={onClose}>
      <div
        className="modal"
        data-testid="matrix-cell-panel"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2>{data.title ?? "角色面板"}</h2>
        <table className="panel-table">
          <thead>
            <tr>
              <th>项目</th>
              <th>生效值</th>
              <th>收到的拐</th>
            </tr>
          </thead>
          <tbody>
            {(data.rows ?? []).map((row) => (
              <tr key={row.key}>
                <td>{row.label}</td>
                <td className="num">{row.value || "—"}</td>
                <td className="num">{row.incoming ? `+${row.incoming}` : ""}</td>
              </tr>
            ))}
            {(data.rows ?? []).length ? null : (
              <tr>
                <td colSpan={3}>—</td>
              </tr>
            )}
          </tbody>
        </table>
        {data.out?.length ? (
          <p className="panel-out">
            给出去：{data.out.map((o) => `${o.label} ${o.value}`).join("；")}
          </p>
        ) : null}
        <div className="modal-actions">
          <button type="button" onClick={onClose}>
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
