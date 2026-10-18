/**
 * 「域对照表」右键单元格的角色面板：复用角色面板的零件（宏表 + 拐力列表），
 * 另外多一段「词条来源统计」（自身算式逐项 + 各来源拐力）。
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import MatrixPanelDialog from "./MatrixPanelDialog";

const DATA = {
  ok: true,
  title: "米c0.factor7 ｜ 奥c0.odette",
  rows: [
    {
      key: "crit_rate",
      label: "暴击率",
      value: "25.000",
      incoming: 0,
      self_terms: [
        { text: "5", value: 5 },
        { text: "20", value: 20 },
      ],
      grants: [],
    },
    {
      key: "atk_pct",
      label: "攻击%",
      value: "143.20",
      incoming: 70,
      self_terms: [
        { text: "24", value: 24 },
        { text: "34.8*2", value: 69.6 },
      ],
      grants: [
        { source: "奥c0.odette", value: 50 },
        { source: "箭头", value: 20 },
      ],
    },
  ],
  out: [{ macro: "em", label: "元素精通", value: 120 }],
};

describe("MatrixPanelDialog", () => {
  it("外壳与角色面板一致（同一个 modal-role-panel + 宏表）", () => {
    render(<MatrixPanelDialog data={DATA} onClose={() => {}} />);
    const dialog = screen.getByTestId("matrix-cell-panel");
    expect(dialog.className).toContain("modal");
    expect(dialog.className).toContain("modal-role-panel");
    expect(dialog.querySelectorAll(".panel-macro-row").length).toBe(2);
  });

  it("词条来源统计：自身算式逐项（纯数字只显示值）+ 各来源拐力", () => {
    render(<MatrixPanelDialog data={DATA} onClose={() => {}} />);
    const block = screen.getByTestId("cell-panel-sources");
    expect(block).toHaveTextContent("词条来源统计");
    // 纯数字项只写数值；算式项保留原样并给出结果
    expect(block).toHaveTextContent("自身 5 + 20");
    expect(block).toHaveTextContent("34.8*2（69.6）");
    // 拐力来源：哪个域给了多少
    expect(block).toHaveTextContent("奥c0.odette +50");
    expect(block).toHaveTextContent("箭头 +20");
  });

  it("没有任何来源时给（无）", () => {
    render(
      <MatrixPanelDialog
        data={{ ok: true, title: "x", rows: [{ key: "em", label: "元素精通", value: "0", incoming: 0 }], out: [] }}
        onClose={() => {}}
      />,
    );
    expect(screen.getByTestId("source-empty")).toHaveTextContent("（无）");
  });

  it("点关闭回调 onClose", () => {
    const onClose = vi.fn();
    render(<MatrixPanelDialog data={DATA} onClose={onClose} />);
    screen.getByText("关闭").click();
    expect(onClose).toHaveBeenCalled();
  });
});
