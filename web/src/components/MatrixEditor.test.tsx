/**
 * 「域对照表」的表格编辑器：百分比基准（双击设置）+ 百分比可视化。
 *
 * Handle 需要 React Flow 的上下文，所以外面套一层 ReactFlowProvider。
 */
import { ReactFlowProvider } from "@xyflow/react";
import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import MatrixEditor from "./MatrixEditor";

const TWO_ROWS = ["a", "b"].join("\n");
const TWO_COLS = ["c", "d"].join("\n");

const TABLE = [
  ["行 \\ 列", "列A", "列B"],
  ["行1", "1,000", "500"],
  ["行2", "2,000", "750"],
];

function setup(props: Partial<React.ComponentProps<typeof MatrixEditor>> = {}) {
  const onBase = vi.fn();
  const view = render(
    <ReactFlowProvider>
      <MatrixEditor
        id="m1"
        rows={TWO_ROWS}
        cols={TWO_COLS}
        fixed=""
        table={TABLE}
        ratios={[
          [100, 50],
          [200, 75],
        ]}
        baseCell="0,0"
        onRows={() => {}}
        onCols={() => {}}
        onFixed={() => {}}
        onBase={onBase}
        {...props}
      />
    </ReactFlowProvider>,
  );
  return { onBase, view };
}

describe("MatrixEditor 百分比基准", () => {
  it("每格显示相对基准的百分比，基准格有标记", () => {
    const { view } = setup();
    const cells = view.container.querySelectorAll(".mx-cell");
    expect(cells).toHaveLength(4);
    expect(cells[0].textContent).toContain("100.0%");   // 基准格
    expect(cells[0].className).toContain("mx-base");
    expect(cells[1].textContent).toContain("50.0%");
    expect(cells[2].textContent).toContain("200.0%");
    expect(cells[3].textContent).toContain("75.0%");
  });

  it("双击任意单元格 → 把它设成基准", () => {
    const { onBase, view } = setup();
    const cells = view.container.querySelectorAll(".mx-cell");
    fireEvent.doubleClick(cells[3]);
    expect(onBase).toHaveBeenCalledWith("1,1");
  });

  it("没设基准时只显示数值，不显示百分比条", () => {
    const { view } = setup({ ratios: null, baseCell: "" });
    expect(view.container.querySelectorAll(".mx-pct")).toHaveLength(0);
    expect(view.container.querySelectorAll(".mx-base")).toHaveLength(0);
  });
});
