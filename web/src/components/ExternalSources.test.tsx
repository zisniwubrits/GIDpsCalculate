/**
 * 「外部域」来源列表：一行一个单行输入框（回车加一行、空行退格删一行）。
 *
 * 为什么单独测组件：这是纯前端交互（键盘、焦点），跟后端无关，
 * 用 RTL 直接按真实按键验证最省事。
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ExternalSources from "./ExternalSources";
// 补全走 /api/external/suggest：测试里给个固定返回，别真发请求
vi.mock("../api", () => ({
  suggestExternal: vi.fn(async () => ({
    ok: true,
    paths: ["data/", "dds.json"],
    domains: [],
  })),
}));

function setup(value = "") {
  const onChange = vi.fn();
  const view = render(
    <ExternalSources id="x1" value={value} onChange={onChange} />,
  );
  return { onChange, view };
}

describe("外部域来源列表", () => {
  it("一行一个输入框；没内容时也留一个空的", () => {
    setup("");
    expect(screen.getByTestId("ext-source-x1-0")).toHaveValue("");
    expect(screen.queryByTestId("ext-source-x1-1")).toBeNull();
  });

  it("存的是多行文本，按行拆成输入框", () => {
    setup("a.json::dds\nb.json::胡桃");
    expect(screen.getByTestId("ext-source-x1-0")).toHaveValue("a.json::dds");
    expect(screen.getByTestId("ext-source-x1-1")).toHaveValue("b.json::胡桃");
  });

  it("回车 → 在下面加一行空输入框", () => {
    const { onChange } = setup("a.json::dds\nb.json::胡桃");
    fireEvent.keyDown(screen.getByTestId("ext-source-x1-0"), { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("a.json::dds\n\nb.json::胡桃");
  });

  it("空行按退格 → 把这一行删掉", () => {
    const { onChange } = setup("a.json::dds\n\nb.json::胡桃");
    fireEvent.keyDown(screen.getByTestId("ext-source-x1-1"), { key: "Backspace" });
    expect(onChange).toHaveBeenCalledWith("a.json::dds\nb.json::胡桃");
  });

  it("非空行按退格不删行（正常删字）", () => {
    const { onChange } = setup("a.json::dds");
    fireEvent.keyDown(screen.getByTestId("ext-source-x1-0"), { key: "Backspace" });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("只有一行时，空行按退格也不会删到没输入框", () => {
    const { onChange } = setup("");
    fireEvent.keyDown(screen.getByTestId("ext-source-x1-0"), { key: "Backspace" });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("改一行只动那一行", () => {
    const { onChange } = setup("a\nb");
    fireEvent.change(screen.getByTestId("ext-source-x1-1"), {
      target: { value: "b.json::胡桃" },
    });
    expect(onChange).toHaveBeenCalledWith("a\nb.json::胡桃");
  });
it("在最后一行按回车：真的多出一个输入框（回归：回车没用）", () => {
    // 以前 sourceLines 会把末尾空行吞掉，于是"新加的那行"下一帧就消失了
    const view = render(
      <ExternalSources id="x2" value="a.json::dds" onChange={() => {}} />,
    );
    expect(view.queryByTestId("ext-source-x2-1")).toBeNull();
    view.rerender(
      <ExternalSources id="x2" value={"a.json::dds\n"} onChange={() => {}} />,
    );
    expect(view.getByTestId("ext-source-x2-1")).toHaveValue("");
  });
it("在中间行打字，光标不会被抢到别的行（回归）", () => {
    // 以前 focusAt 用完不清，且写在 ref 回调里：每次重渲染都 focus 那一行，
    // 于是"在别的行打字，光标跳到那行末尾"。
    const onChange = vi.fn();
    const view = render(
      <ExternalSources id="x3" value="a\nb\nc" onChange={onChange} />,
    );
    // 先引发一次"插入"（focusAt 被设上），再把值换回来模拟后续重渲染
    fireEvent.keyDown(view.getByTestId("ext-source-x3-0"), { key: "Enter" });
    view.rerender(<ExternalSources id="x3" value="a\nb\nc" onChange={onChange} />);
    view.rerender(<ExternalSources id="x3" value="a\nb2\nc" onChange={onChange} />);
    // 焦点不该被这类重渲染抢走（jsdom 里没人主动 focus 就还是 body）
    expect(document.activeElement?.tagName ?? "BODY").not.toBe("INPUT");
  });

  it("输入时弹出补全小弹窗（候选由 SourceInput 负责）", async () => {
    const onChange = vi.fn();
    render(<ExternalSources id="x4" value="" onChange={onChange} />);
    fireEvent.change(screen.getByTestId("ext-source-x4-0"), {
      target: { value: "da" },
    });
    // 防抖之后才请求；弹窗挂在 body 上
    const pop = await screen.findByTestId("ext-source-x4-0-hints");
    expect(pop.querySelectorAll(".src-pop-item").length).toBeGreaterThan(0);
  });

  it("点候选：路径替换 `::` 之前那段，`::` 之后保持不动", async () => {
    const onChange = vi.fn();
    render(<ExternalSources id="x5" value="da::dds" onChange={onChange} />);
    const el = screen.getByTestId("ext-source-x5-0");
    fireEvent.change(el, { target: { value: "da" } });
    await screen.findByTestId("ext-source-x5-0-hints");
    fireEvent.mouseDown(screen.getByTestId("ext-source-x5-0-hint-data/"));
    // 值来自 props（"da::dds"）：换掉 :: 之前那段，保留 ::dds
    expect(onChange).toHaveBeenCalledWith("data/::dds");
  });

  it("焦点离开后补全弹窗自动消失", async () => {
    const onChange = vi.fn();
    render(<ExternalSources id="x6" value="" onChange={onChange} />);
    const input = screen.getByTestId("ext-source-x6-0");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "da" } });
    await screen.findByTestId("ext-source-x6-0-hints");

    fireEvent.blur(input);
    expect(screen.queryByTestId("ext-source-x6-0-hints")).toBeNull();
  });
});
