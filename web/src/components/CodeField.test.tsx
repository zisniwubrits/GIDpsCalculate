/**
 * 带高亮的文本框：下层副本负责上色，textarea 只负责编辑（值是唯一真相）。
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CodeField from "./CodeField";

describe("CodeField", () => {
  it("把关键字渲染成深蓝片段，textarea 里仍是原文", () => {
    const { container } = render(
      <CodeField value="atk = own::atk + in::atk" onChange={() => {}} macros={["atk"]} testId="defs-x" />,
    );
    const kws = [...container.querySelectorAll(".tok-kw")].map((el) => el.textContent);
    expect(kws).toEqual(["own", "in"]);
    const macros = [...container.querySelectorAll(".tok-macro")].map((el) => el.textContent);
    expect(macros).toEqual(["atk", "atk", "atk"]);
    expect(screen.getByTestId("defs-x")).toHaveValue("atk = own::atk + in::atk");
  });

  it("改动照常往上抛（值不变形）", () => {
    const onChange = vi.fn();
    render(<CodeField value="a" onChange={onChange} testId="defs-y" />);
    fireEvent.change(screen.getByTestId("defs-y"), { target: { value: "a\nb" } });
    expect(onChange).toHaveBeenCalledWith("a\nb");
  });
});
