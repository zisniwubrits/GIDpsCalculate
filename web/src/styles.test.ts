/**
 * 样式契约测试：只断言「几条必须存在的关键声明」，作为廉价的可视回归保险。
 *
 * 为什么值得写：卡片尺寸/边框这类问题在 jsdom 里跑不出可视结果（vitest 不加载 CSS），
 * 但历史上真出过事故 —— `.card` 少写 `height: 100%` 导致「纵向缩放看起来没反应」。
 * 这里直接把关键声明钉住，改动样式时能立刻发现。
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/** 直接读源文件（vitest 里 `css: false`，`?raw` 导入拿不到内容）。 */
function loadStyles(): string {
  const candidates = [
    resolve(process.cwd(), "src/styles.css"),
    resolve(process.cwd(), "web/src/styles.css"),
  ];
  for (const path of candidates) {
    try {
      return readFileSync(path, "utf8");
    } catch {
      /* 换下一个候选路径 */
    }
  }
  throw new Error(`找不到 styles.css，试过：${candidates.join(" , ")}`);
}

/** 去掉注释后再匹配，否则形如 `/* … *\/\n.selector {` 的规则会漏掉。 */
const css = loadStyles().replace(/\/\*[\s\S]*?\*\//g, "");

/** 取出某个选择器的规则体；选择器要写成 `.card`、`.card-body.bare` 这种精确形式。 */
function ruleBody(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(`(?:^|\\})\\s*${escaped}\\s*\\{([^}]*)\\}`).exec(css);
  if (!match) throw new Error(`styles.css 里找不到规则：${selector}`);
  return match[1];
}

describe("卡片尺寸", () => {
  it(".card 同时撑满容器宽高（少了 height 纵向缩放就没反应）", () => {
    const body = ruleBody(".card");
    expect(body).toMatch(/width:\s*100%/);
    expect(body).toMatch(/height:\s*100%/);
  });

  it("卡片主体可滚动，卡片拉高/压矮时内容不会溢出", () => {
    const body = ruleBody(".card-body");
    expect(body).toMatch(/overflow:\s*auto/);
    expect(body).toMatch(/min-height:\s*0/);
  });
});

describe("文本卡片（便签式）", () => {
  it("内边距比普通卡片小", () => {
    expect(ruleBody(".card-body-bare")).toMatch(/padding:\s*2px\s+4px/);
  });

  it("文本框随卡片铺满：便签行要覆盖 .f-row 的 align-items: start", () => {
    // `.f-row`（普通卡：文本框保持自己的行数，卡片拉高不跟着变长）与 `.f-row-bare`
    // 是挂在同一个 div 上的组合类名；少了这边的 stretch，便签卡文本框永远只有 2 行高、
    // 卡片拉高只留一片空白（用户报过这个问题）。
    expect(ruleBody(".f-row-bare")).toMatch(/align-items:\s*stretch/);
  });

  it("去掉输入框边框，且不再抢右下角的缩放手柄", () => {
    const bare = ruleBody(".f-bare");
    expect(bare).toMatch(/border:\s*none/);
    expect(bare).toMatch(/background:\s*transparent/);
    // resize 必须写在 `.f-area.f-bare`（两个类）里：`.f-bare` 单独写在文件前面，
    // 同等优先级的 `.f-area { resize: vertical }` 会把它覆盖掉，文本框又能被拖高。
    expect(ruleBody(".f-area.f-bare")).toMatch(/resize:\s*none/);
  });
});

describe("字体", () => {
  it("多行文本框不单独指定字体族（否则中文会回退成宋体）", () => {
    // textarea 靠全局的 `font: inherit` 跟随界面字体；这里再写 font-family 就会
    // 因为 Consolas 等无中文字形而让中文变成宋体（用户报过这个现象）。
    expect(ruleBody(".f-area")).not.toMatch(/font-family/);
  });

  it("等宽表格的字栈里带中文字体，避免中文回退成宋体", () => {
    const body = ruleBody(".dtable-mono .dtable-cell");
    expect(body).toMatch(/font-family/);
    expect(body).toMatch(/Microsoft YaHei/);
  });
});
