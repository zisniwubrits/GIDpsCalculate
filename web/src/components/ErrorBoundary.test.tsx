/** 错误边界：渲染期异常要变成可读卡片，而不是白屏。 */
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ErrorBoundary from "./ErrorBoundary";

function Boom(): never {
  throw new Error("模拟渲染异常");
}

describe("ErrorBoundary", () => {
  beforeEach(() => {
    // React 会把错误打到 console.error，测试里静音（否则输出很吵）
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("子组件抛异常时显示错误卡片与错误信息（不再白屏）", () => {
    render(
      <ErrorBoundary hint="提示：重启后端试试">
        <Boom />
      </ErrorBoundary>,
    );

    expect(screen.getByTestId("crash")).toBeInTheDocument();
    expect(screen.getByText("界面出错了")).toBeInTheDocument();
    expect(screen.getByText("模拟渲染异常")).toBeInTheDocument();
    expect(screen.getByText("提示：重启后端试试")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新加载" })).toBeInTheDocument();
  });

  it("没出错时原样渲染子组件", () => {
    render(
      <ErrorBoundary>
        <p>一切正常</p>
      </ErrorBoundary>,
    );

    expect(screen.getByText("一切正常")).toBeInTheDocument();
    expect(screen.queryByTestId("crash")).toBeNull();
  });
});
