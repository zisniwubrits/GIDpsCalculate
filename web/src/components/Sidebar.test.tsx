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
import Toolbar from "./Toolbar";

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

describe("工具栏开关", () => {
  const renderToolbar = (overrides: Partial<Parameters<typeof Toolbar>[0]> = {}) => {
    const props = {
      name: "工程",
      onName: vi.fn(),
      saveDir: "",
      dirty: false,
      canUndo: false,
      canRedo: false,
      onUndo: vi.fn(),
      onRedo: vi.fn(),
      onSave: vi.fn(),
      onOpen: vi.fn(),
      onExport: vi.fn(),
      onNewProject: vi.fn(),
      onHelp: vi.fn(),
      zoom: 1,
      onZoomIn: vi.fn(),
      onZoomOut: vi.fn(),
      onZoomReset: vi.fn(),
      onFit: vi.fn(),
      boxSelectDomains: false,
      onToggleBoxSelectDomains: vi.fn(),
      showDomainArrows: true,
      onToggleShowDomainArrows: vi.fn(),
      status: { kind: "ok" as const, text: "就绪" },
      ...overrides,
    };
    render(<Toolbar {...props} />);
    return props;
  };

  it("两个开关都是 tb-toggle 按钮：框选域默认关、域间箭头默认开", () => {
    const props = renderToolbar();
    const box = screen.getByTestId("box-select-domains");
    const arrows = screen.getByTestId("show-domain-arrows");
    expect(box).toHaveClass("tb-toggle");
    expect(box).toHaveAttribute("aria-pressed", "false");
    // 域间箭头默认显示（与原来的行为一致），所以默认就是按下状态
    expect(arrows).toHaveClass("tb-toggle");
    expect(arrows).toHaveAttribute("aria-pressed", "true");
    expect(arrows).toHaveClass("on");
    screen.getByTestId("show-domain-arrows").click();
    expect(props.onToggleShowDomainArrows).toHaveBeenCalledTimes(1);
  });

  it("关掉域间箭头后按钮不高亮", () => {
    renderToolbar({ showDomainArrows: false });
    const arrows = screen.getByTestId("show-domain-arrows");
    expect(arrows).toHaveAttribute("aria-pressed", "false");
    expect(arrows).not.toHaveClass("on");
  });
});
