/**
 * 侧栏「选中的卡片」区：对齐按钮是六个方向，且至少选两张才可用。
 *
 * 为什么单独测组件而不在 App 里测：框选/点选依赖 React Flow 的指针事件，
 * jsdom 里选不中卡片（d3-drag 还是 stub），组件级测反而更贴近真实契约。
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import fixture from "../test/schema.fixture.json";
import type { Schema } from "../types";
import Sidebar from "./Sidebar";

const schema = fixture as unknown as Schema;

function renderSidebar(selectedCount: number) {
  const onAlign = vi.fn();
  render(
    <Sidebar
      schema={schema}
      selectedCount={selectedCount}
      onAdd={() => undefined}
      onPreset={() => undefined}
      onAlign={onAlign}
      onClearSelection={() => undefined}
    />,
  );
  return { onAlign };
}

describe("侧栏对齐按钮", () => {
  it("六个方向都在：左 / 右 / 顶 / 底 / 水平居中 / 垂直居中", () => {
    renderSidebar(2);
    for (const label of ["左对齐", "右对齐", "顶对齐", "底对齐", "水平居中", "垂直居中"]) {
      expect(screen.getByRole("button", { name: label })).toBeEnabled();
    }
  });

  it("少于两张时禁用（对齐至少要有个参照）", () => {
    renderSidebar(1);
    for (const label of ["左对齐", "右对齐", "顶对齐", "底对齐", "水平居中", "垂直居中"]) {
      expect(screen.getByRole("button", { name: label })).toBeDisabled();
    }
  });
});
