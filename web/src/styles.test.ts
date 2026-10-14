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

/**
 * 同上，但允许选择器写成**逗号列表**（`a, b { … }` 这种 ruleBody 匹配不到）。
 * 做法是按 `}` 切开逐段看选择器列表里有没有它。
 */
function ruleBodyInList(selector: string): string {
  for (const chunk of css.split("}")) {
    const i = chunk.lastIndexOf("{");
    if (i < 0) continue;
    const sels = chunk.slice(0, i).split(",").map((s) => s.trim());
    if (sels.includes(selector)) return chunk.slice(i + 1);
  }
  throw new Error(`styles.css 的选择器列表里找不到：${selector}`);
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
  it("F1 教程不单独指定字体族（否则中文会回退成宋体，与界面不一致）", () => {
    // 教程靠 pre-wrap 保排版，不需要等宽；字体族统一由下面那条全局 pre 规则继承。
    expect(ruleBody(".help-text")).not.toMatch(/font-family/);
  });

  it("pre/code 显式继承界面字体 —— <pre> 的 UA 默认是 monospace，中文会回退成宋体", () => {
    // 只删掉自定义 font-family 是没用的：浏览器给 <pre> 的默认样式就是 monospace，
    // 中文 Windows 上 monospace 的中文字形是宋体（用户报过「F1 还是宋体」）。
    for (const sel of ["pre", "code", "kbd", "samp"]) {
      expect(ruleBodyInList(sel)).toMatch(/font-family:\s*inherit/);
    }
  });
});

describe("表格：列宽对齐 + 表头吸顶 + 填满卡片", () => {
  it("整表用一个 grid，行盒子不生成盒子 —— 这是列宽上下对齐的关键", () => {
    // 之前是「每行各自 flex（flex: 1 1 auto）」，各行按本行内容算宽度，
    // 同一列在上下行宽度不同 → 竖线对不齐（用户报过）。
    expect(ruleBody(".dtable")).toMatch(/display:\s*grid/);
    expect(ruleBody(".dtable-row")).toMatch(/display:\s*contents/);
  });

  it("表格随卡片变高、超出才在自己内部滚动（不再限制 320px 死高）", () => {
    const body = ruleBody(".dtable");
    expect(body).toMatch(/flex:\s*1\s+1\s+auto/);
    expect(body).toMatch(/min-height:\s*0/);
    expect(body).toMatch(/overflow:\s*auto/);
    expect(body).not.toMatch(/max-height/);
  });

  it("表头吸顶，滚动时列名还在", () => {
    const body = ruleBody(".dtable-th");
    expect(body).toMatch(/position:\s*sticky/);
    expect(body).toMatch(/top:\s*0/);
  });

  it("表格卡片的字段区不自己滚（否则卡片与表格两条滚动条）", () => {
    expect(ruleBody(".card-body-table")).toMatch(/overflow:\s*hidden/);
  });

  it("单元格不再用 flex 宽度，并且超宽时省略号而不是撑开列", () => {
    const body = ruleBody(".dtable-cell");
    expect(body).not.toMatch(/flex:/);
    expect(body).toMatch(/text-overflow:\s*ellipsis/);
  });
});

describe("角色容器面板", () => {
  it("虚线淡蓝底板：一眼区分「面板」与普通白卡，画布点阵能透出来", () => {
    const body = ruleBody(".card-role-box");
    expect(body).toMatch(/border:\s*1px\s+dashed/);
    expect(body).toMatch(/background:\s*rgba\(/);
    expect(body).toMatch(/box-shadow:\s*none/);
  });

  it("标题栏上的角色徽标是小胶囊（不抢卡片标题）", () => {
    const body = ruleBody(".card-role-chip");
    expect(body).toMatch(/border-radius/);
    expect(body).toMatch(/font-size:\s*11px/);
  });

  it("背景标记的标签条是「标记牌」而不是卡片头（小胶囊、贴在左上角）", () => {
    const head = ruleBody(".card-role-box .card-head");
    expect(head).toMatch(/align-self:\s*flex-start/);
    expect(head).toMatch(/border-radius/);
    // 用户要求"标签控件不改变，只是变大" → 11px 提到 12px、内边距加大
    expect(head).toMatch(/font-size:\s*12px/);
    expect(head).toMatch(/padding:\s*3px 10px/);
    expect(head).toMatch(/border-bottom:\s*none/);
  });

  it("角色名输入框只占一小段，不铺满整个区域", () => {
    const body = ruleBody(".card-role-box .f-input");
    expect(body).toMatch(/width:\s*140px/);
  });

  it("角色面板整体不吃鼠标事件（否则光标是抓手、在面板上拖不出框选），标题栏/手柄/输入框单独放行", () => {
    // 这条必须设在**节点元素**上：pointer-events 只对设它的元素生效，祖先仍会被命中，
    // 所以设在 .card-body 上是没用的（上一版就踩过这个）。
    expect(ruleBody(".react-flow__node.node-role-box")).toMatch(/pointer-events:\s*none/);
    for (const sel of [
      ".react-flow__node.node-role-box .card-head",
      ".react-flow__node.node-role-box .react-flow__resize-control",
      ".react-flow__node.node-role-box .react-flow__handle",
      ".react-flow__node.node-role-box input",
    ]) {
      expect(ruleBodyInList(sel)).toMatch(/pointer-events:\s*auto/);
    }
  });

  it("命名卡片的徽标同样是小胶囊，且用等宽字形（显示的是要敲的前缀 `名字::`）", () => {
    const body = ruleBody(".card-name-chip");
    expect(body).toMatch(/border-radius/);
    expect(body).toMatch(/font-size:\s*11px/);
    expect(body).toMatch(/font-family/);
  });

  it("角色标记：标记牌 + 角色名 + 面板合成同一张卡片（角色名在面板上面）", () => {
    // 三块片段共用同一张卡片的底色与左右描边（拼成一个连续的盒子）
    const merged = ruleBodyInList(".card-role-box > .role-panel");
    expect(merged).toMatch(/background:\s*var\(--card-bg\)/);
    expect(merged).toMatch(/border-left:\s*1px solid var\(--line\)/);
    expect(merged).toMatch(/border-right:\s*1px solid var\(--line\)/);
    // 标记牌出上圆角与标题底色
    const head = ruleBody(".card-role-box > .card-head");
    expect(head).toMatch(/border-radius:\s*8px 8px 0 0/);
    expect(head).toMatch(/font-size:\s*12px/);
    // 相对位置保持原样：**不重排**（曾经用 order 把角色名提到面板前，用户要求改回来）
    expect(ruleBody(".card-role-box > .card-body")).not.toMatch(/order:/);
    expect(ruleBody(".card-role-box > .role-panel")).not.toMatch(/order:/);
    // 角色名一行只带左右描边 → 与标牌、面板连成一张卡片
    expect(ruleBody(".card-role-box > .card-body")).toMatch(/padding:\s*4px 7px/);
    const panel = ruleBody(".card-role-box > .role-panel");
    expect(panel).toMatch(/border-bottom:\s*1px solid var\(--line\)/);
    expect(panel).toMatch(/border-radius:\s*0 0 8px 8px/);
    // 面板内部：一行一个属性，字段名灰、数值右对齐，含拐暖色
    expect(ruleBody(".role-panel .rp-row")).toMatch(/grid-template-columns:\s*84px 1fr/);
    expect(ruleBody(".role-panel .rp-key")).toMatch(/color:\s*var\(--muted\)/);
    expect(ruleBody(".role-panel .rp-val")).toMatch(/text-align:\s*right/);
    expect(ruleBody(".role-panel .rp-buffed")).toMatch(/color:\s*var\(--warn\)/);
  });

  it("角色面板弹窗放大、宏表一行一个（便于交互）", () => {
    // 弹窗要够宽（14 行 × 4 列铺开）
    const modal = ruleBody(".modal-role-panel");
    expect(modal).toMatch(/width:\s*min\(9\d\dpx/);
    // 单列 = 一行一个宏（不是并排两列）
    const grid = ruleBody(".panel-macro-grid");
    expect(grid).toMatch(/grid-template-columns:\s*1fr/);
    expect(grid).not.toMatch(/repeat\(2/);
    // 行内输入框加大，便于点选与输入
    const input = ruleBody(".panel-macro-row input");
    expect(input).toMatch(/padding:\s*6px/);
    // 「喂给哪张卡」直接显示
    expect(ruleBody(".pm-feed")).toMatch(/text-overflow:\s*ellipsis/);
    // 行内五列**必须一行放下**：宏 / 属性 / 值 / 喂给哪张卡 / 显示（勾选框）
    // （曾经因为另一处的 4 列声明排在后面覆盖，勾选框被挤到第二行）
    const row = ruleBody(".panel-macro-row");
    expect(row).toMatch(/grid-template-columns:[^;]*\)\s*40px/);
    expect(row).toMatch(/align-items:\s*center/);
    // 表头列宽与数据行一致，否则标题对不上
    expect(ruleBody(".panel-macro-head")).toMatch(/grid-template-columns:[^;]*\)\s*40px/);
  });

  it("拐力端口并排在左上角标签正上方（箭头的始末都落在标签上方）", () => {
    // Position.Top 只把端口放在水平中点，真正"抬到标签上方、左右并排"靠这两条
    const portIn = ruleBody(".react-flow__handle.role-port-in");
    const portOut = ruleBody(".react-flow__handle.role-port-out");
    expect(portIn).toMatch(/top:\s*-\d+px/);        // 负偏移 = 在卡片上边缘之上
    expect(portOut).toMatch(/top:\s*-\d+px/);
    const inLeft = Number(/left:\s*(\d+)px/.exec(portIn)?.[1] ?? NaN);
    const outLeft = Number(/left:\s*(\d+)px/.exec(portOut)?.[1] ?? NaN);
    expect(inLeft).toBeGreaterThan(0);
    expect(outLeft).toBeGreaterThan(inLeft);        // 一进一出并排（出在右边）
    expect(outLeft - inLeft).toBeLessThan(120);     // 都挤在左上角那一小块
  });

  it("拐力箭头画成蓝色虚线，与伤害连线区分（不用暖色）", () => {
    const body = ruleBody(".react-flow__edge-path.card-edge-buff");
    expect(body).toMatch(/stroke-dasharray/);
    expect(body).toMatch(/stroke:\s*var\(--link\)/);
    expect(body).not.toMatch(/--warn/);
  });
});

describe("工具栏状态区", () => {
  it("构建时间是小号 muted 文本（不抢眼，但核对旧包时要用）", () => {
    const body = ruleBody(".tb-build");
    expect(body).toMatch(/font-size:\s*11px/);
    expect(body).toMatch(/color:\s*var\(--muted\)/);
    expect(body).toMatch(/white-space:\s*nowrap/);
  });
});

describe("画布水印", () => {  it("铺满整块画布：必须显式 width/height 100%，否则 <svg> 只用固有尺寸 300×150", () => {
    // 实测踩过：<svg> 是替换元素，只写 inset:0 而宽高 auto 时按规范取固有尺寸
    // 300×150 → 水印只画在左上角一小块，用户"看不到水印"。
    const body = ruleBody(".canvas-watermark");
    expect(body).toMatch(/width:\s*100%/);
    expect(body).toMatch(/height:\s*100%/);
    expect(body).toMatch(/position:\s*absolute/);
    expect(body).toMatch(/inset:\s*0/);
    expect(body).toMatch(/pointer-events:\s*none/);
  });

  it("位于画布最底层（-2）：点阵 -1、卡片在 .react-flow__renderer(4) 里", () => {
    // React Flow 给 .react-flow 打内联 `position: relative; z-index: 0`，
    // 它自身就是层叠上下文，所以用负数安全（实测过 RF 的内联样式）；
    // 点阵背景是 portal 插进来的、固定在水印之前，只能靠 z-index 分先后。
    expect(ruleBody(".canvas-watermark")).toMatch(/z-index:\s*-2/);
  });

  it("水印是比背景略深的浅蓝色实色（不靠透明度压淡，免得看不见）", () => {
    const body = ruleBody(".canvas-watermark .wm-text");
    expect(body).toMatch(/fill:\s*#cfe0f0/);
    expect(body).not.toMatch(/fill-opacity/);
    // 字号由组件按画布单位给出，样式里不写死，免得两处打架
    expect(body).not.toMatch(/font-size/);
  });
});
