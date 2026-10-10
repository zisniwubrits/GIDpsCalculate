/** 表格卡片（理想圣遗物 / 变量表）的选中与复制行为。 */
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import DataTable, { selectionText } from "./DataTable";

const header = ["属性", "强化区间", "最高区间", "平均值"];
const rows = [
  ["暴击率（%）", "2.72/3.11", "16.32~23.34", "3.305"],
  ["暴击伤害（%）", "5.44/6.22", "32.64~46.62", "6.605"],
];

describe("selectionText", () => {
  it("未选中时给整表（含表头）", () => {
    expect(selectionText(header, rows, null)).toBe(
      [header, ...rows].map((r) => r.join("\t")).join("\n"),
    );
  });

  it("单格只复制原文", () => {
    expect(selectionText(header, rows, { a: { r: 0, c: 1 }, b: { r: 0, c: 1 } })).toBe(
      "2.72/3.11",
    );
  });

  it("多格复制为 TSV", () => {
    expect(selectionText(header, rows, { a: { r: 0, c: 0 }, b: { r: 1, c: 1 } })).toBe(
      "暴击率（%）\t2.72/3.11\n暴击伤害（%）\t5.44/6.22",
    );
  });

  it("反向拖动也能正确取区域", () => {
    expect(selectionText(header, rows, { a: { r: 1, c: 1 }, b: { r: 0, c: 0 } })).toBe(
      "暴击率（%）\t2.72/3.11\n暴击伤害（%）\t5.44/6.22",
    );
  });
});

describe("DataTable", () => {
  it("渲染表头与正文", () => {
    render(<DataTable header={header} rows={rows} testId="t" />);
    expect(screen.getByRole("columnheader", { name: "属性" })).toBeInTheDocument();
    expect(screen.getAllByRole("gridcell")).toHaveLength(8);
  });

  it("点单元格高亮，Ctrl+C 复制该格", async () => {
    const user = userEvent.setup();
    const spy = vi.spyOn(navigator.clipboard, "writeText");
    render(<DataTable header={header} rows={rows} testId="t" />);
    const cell = screen.getByText("2.72/3.11");
    await user.click(cell);
    expect(cell).toHaveClass("dtable-sel");
    await user.keyboard("{Control>}c{/Control}");
    expect(spy).toHaveBeenCalledWith("2.72/3.11");
  });

  it("整表用一套 grid 列轨道（列宽才能上下对齐）", () => {
    render(<DataTable header={header} rows={rows} testId="t" />);
    // 4 列表头 → 4 条轨道；行盒子是 display:contents，不再各算各的宽度
    expect(screen.getByTestId("t").style.gridTemplateColumns).toBe(
      "repeat(4, minmax(62px, 1fr))",
    );
  });

  it("变量表（mono）列的最小宽度更宽，方便看数字", () => {
    render(<DataTable header={["变量", "值"]} rows={[["攻击力", "1000"]]} mono testId="m" />);
    expect(screen.getByTestId("m").style.gridTemplateColumns).toBe(
      "repeat(2, minmax(78px, 1fr))",
    );
  });

  it("拖动可选中矩形区域", () => {
    const spy = vi.spyOn(navigator.clipboard, "writeText");
    render(<DataTable header={header} rows={rows} testId="t" />);
    const table = screen.getByTestId("t");
    fireEvent.mouseDown(screen.getByText("暴击率（%）"));
    fireEvent.mouseEnter(screen.getByText("6.605"));
    fireEvent.mouseUp(screen.getByText("6.605"));
    fireEvent.keyDown(table, { key: "c", ctrlKey: true });

    expect(spy).toHaveBeenCalledWith(
      "暴击率（%）\t2.72/3.11\t16.32~23.34\t3.305\n暴击伤害（%）\t5.44/6.22\t32.64~46.62\t6.605",
    );
  });
});
