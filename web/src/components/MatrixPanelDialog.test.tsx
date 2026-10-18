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
  sources: [
    { macro: "crit_rate", label: "暴击率", value: 25, source: "自身" },
    { macro: "atk_pct", label: "攻击%", value: 143.2, source: "自身" },
    { macro: "atk_pct", label: "攻击%", value: 50, source: "奥c0.odette" },
    { macro: "atk_pct", label: "攻击%", value: 20, source: "箭头" },
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

  it("词条来源统计：一行一个来源（属性 数值 来源），与角色面板同一段代码", () => {
    render(<MatrixPanelDialog data={DATA} onClose={() => {}} />);
    const block = screen.getByTestId("cell-panel-sources");
    expect(block).toHaveTextContent("词条来源统计");
    // 与角色面板的 OUT/IN 用同一个 BuffRows（.buff-list），一行一个来源
    const items = [...block.querySelectorAll(".buff-list li")].map((li) => li.textContent);
    expect(items).toEqual([
      "暴击率25自身",
      "攻击%143.2自身",
      "攻击%50奥c0.odette",
      "攻击%20箭头",
    ]);
  });

  it("没有任何来源时给（无）", () => {
    render(
      <MatrixPanelDialog
        data={{ ok: true, title: "x", rows: [], sources: [], out: [] }}
        onClose={() => {}}
      />,
    );
    expect(screen.getByTestId("cell-panel-sources-empty")).toHaveTextContent("（无）");
  });

  it("点关闭回调 onClose", () => {
    const onClose = vi.fn();
    render(<MatrixPanelDialog data={DATA} onClose={onClose} />);
    screen.getByText("关闭").click();
    expect(onClose).toHaveBeenCalled();
  });
});
