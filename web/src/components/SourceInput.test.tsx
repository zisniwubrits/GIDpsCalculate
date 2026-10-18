/**
 * 来源输入框：单行输入 + 小弹窗补全（不再把候选排在输入框下面）。
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../api", () => ({
  suggestExternal: vi.fn(async (q: string) => ({
    ok: true,
    paths: q.includes("::") ? [] : ["data/", "炉火.json"],
    domains: q.includes("::") ? ["mutual", "self"] : [],
  })),
}));

import SourceInput from "./SourceInput";

const type = (el: HTMLElement, value: string) =>
  fireEvent.change(el, { target: { value } });

describe("SourceInput", () => {
  it("输入后弹小弹窗给路径候选，点一下就填进去", async () => {
    const onChange = vi.fn();
    render(<SourceInput value="" onChange={onChange} testId="s1" />);
    type(screen.getByTestId("s1"), "炉");
    const pop = await screen.findByTestId("s1-hints");
    expect(pop.querySelectorAll(".src-pop-item").length).toBeGreaterThan(0);
    // 选中**文件**时会自动补上 `::`（紧接着弹域名候选；多域文件不写域名读不到拐力）
    fireEvent.mouseDown(screen.getByTestId("s1-hint-炉火.json"));
    expect(onChange).toHaveBeenCalledWith("炉火.json::");
  });

  it("光标在 :: 后面补域名，只替换域名那一段", async () => {
    const onChange = vi.fn();
    render(<SourceInput value="a.json::" onChange={onChange} testId="s2" />);
    // 光标放在末尾（:: 之后）
    const el = screen.getByTestId("s2") as HTMLInputElement;
    el.setSelectionRange(el.value.length, el.value.length);
    type(el, "a.json::m");
    await waitFor(async () =>
      expect(screen.getByTestId("s2-hints")).toBeInTheDocument(),
    );
    fireEvent.mouseDown(screen.getByTestId("s2-hint-mutual"));
    expect(onChange).toHaveBeenCalledWith("a.json::mutual");
  });

  it("回车交给调用方（加一行），退格只在空输入时交给调用方（删一行）", () => {
    const onEnter = vi.fn();
    const onDelete = vi.fn();
    const { rerender } = render(
      <SourceInput value="a" onChange={() => {}} onEnter={onEnter} onEmptyBackspace={onDelete} testId="s3" />,
    );
    fireEvent.keyDown(screen.getByTestId("s3"), { key: "Enter" });
    expect(onEnter).toHaveBeenCalled();
    fireEvent.keyDown(screen.getByTestId("s3"), { key: "Backspace" });
    expect(onDelete).not.toHaveBeenCalled();          // 非空：正常删字

    rerender(
      <SourceInput value="" onChange={() => {}} onEnter={onEnter} onEmptyBackspace={onDelete} testId="s3" />,
    );
    fireEvent.keyDown(screen.getByTestId("s3"), { key: "Backspace" });
    expect(onDelete).toHaveBeenCalled();              // 空行：交给调用方删掉
  });

  it("失焦后弹窗收起", async () => {
    render(<SourceInput value="" onChange={() => {}} testId="s4" />);
    type(screen.getByTestId("s4"), "炉");
    await screen.findByTestId("s4-hints");
    fireEvent.blur(screen.getByTestId("s4"));
    expect(screen.queryByTestId("s4-hints")).toBeNull();
  });
it("选中目录不加 `::`（要继续往里输入）", async () => {
    const onChange = vi.fn();
    render(<SourceInput value="" onChange={onChange} testId="s5" />);
    type(screen.getByTestId("s5"), "da");
    await screen.findByTestId("s5-hints");
    fireEvent.mouseDown(screen.getByTestId("s5-hint-data/"));
    expect(onChange).toHaveBeenCalledWith("data/");
  });
});
