/**
 * 关键字高亮：own/out/in 深蓝、面板宏名同色系；`atk_pct` 不会被切出 `atk`。
 */
import { describe, expect, it } from "vitest";
import { highlightTokens } from "./model";

const MACROS = ["atk", "atk_pct", "crit_rate", "em", "dmg"];

const kinds = (text: string) => highlightTokens(text, MACROS).map((t) => [t.kind, t.text]);

describe("变量卡关键字高亮", () => {
  it("own / out / in 是关键字", () => {
    expect(kinds("out::atk_pct = 40")).toEqual([
      ["kw", "out"],
      ["plain", "::"],
      ["macro", "atk_pct"],
      ["plain", " = 40"],
    ]);
    expect(kinds("atk = own::atk + in::atk")).toEqual([
      ["macro", "atk"],
      ["plain", " = "],
      ["kw", "own"],
      ["plain", "::"],
      ["macro", "atk"],
      ["plain", " + "],
      ["kw", "in"],
      ["plain", "::"],
      ["macro", "atk"],
    ]);
  });

  it("长宏名优先：atk_pct 不会被拆成 atk + _pct", () => {
    const got = highlightTokens("atk_pct = 12", MACROS);
    expect(got.map((t) => t.text)).toEqual(["atk_pct", " = 12"]);
    expect(got[0].kind).toBe("macro");
  });

  it("贴着别的标识符就不算关键字（避免误伤）", () => {
    // "out" 出现在 "outside" 里不算；"my_atk" 里的 atk 也不算
    expect(kinds("outside = my_atk").every(([k]) => k === "plain")).toBe(true);
  });

  it("空文本返回空数组", () => {
    expect(highlightTokens("", MACROS)).toEqual([]);
    expect(highlightTokens(null, MACROS)).toEqual([]);
  });
});
