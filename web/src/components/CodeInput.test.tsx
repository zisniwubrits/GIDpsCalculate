/**
 * 单行高亮输入框：卡片里的数值 / 百分比 / 文本字段（例如「抗性区」的敌人抗性）
 * 也能把 own / out / in 与面板宏名高亮出来。
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CodeInput from "./CodeInput";

describe("CodeInput", () => {
  it("关键字与宏名分色渲染，输入框里仍是原文", () => {
    const { container } = render(
      <CodeInput
        value="atk*1.5 + in::dmg"
        onChange={() => {}}
        macros={["atk", "dmg"]}
        testId="f1"
      />,
    );
    expect([...container.querySelectorAll(".tok-kw")].map((e) => e.textContent)).toEqual(["in"]);
    expect([...container.querySelectorAll(".tok-macro")].map((e) => e.textContent)).toEqual([
      "atk",
      "dmg",
    ]);
    expect(screen.getByTestId("f1")).toHaveValue("atk*1.5 + in::dmg");
  });

  it("改动照常往上抛", () => {
    const onChange = vi.fn();
    render(<CodeInput value="" onChange={onChange} testId="f2" />);
    fireEvent.change(screen.getByTestId("f2"), { target: { value: "own::em*2" } });
    expect(onChange).toHaveBeenCalledWith("own::em*2");
  });

  it("没有关键字时只渲染原文（不会多出空片段）", () => {
    const { container } = render(<CodeInput value="1000" onChange={() => {}} />);
    expect(container.querySelectorAll(".tok-kw").length).toBe(0);
    expect(container.querySelectorAll(".tok-macro").length).toBe(0);
    expect(container.querySelector(".code-hl-line")?.textContent).toBe("1000");
  });
});
