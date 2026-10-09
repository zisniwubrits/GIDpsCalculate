/**
 * 端到端（jsdom）集成测试：真实 App + 真实 schema，只把后端 fetch 换成本地假实现。
 *
 * 覆盖：schema 驱动渲染、加卡片、改字段触发重算、预设、删除、撤销/重做、
 * 结果变量弹窗、导出工程 / 结果、未保存标记、F1 教程、localStorage 自动保存。
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { downloadText, pickTextFile } from "./download";
import { CARD_DRAG_HANDLE } from "./model";
import type { EvaluateResult, GraphJSON, Schema } from "./types";
import fixture from "./test/schema.fixture.json";

vi.mock("./download", () => ({
  downloadText: vi.fn(),
  pickTextFile: vi.fn(async () => null),
}));

const schema = fixture as unknown as Schema;
const mockedDownload = vi.mocked(downloadText);
const mockedPick = vi.mocked(pickTextFile);

const jsonResponse = (data: unknown) =>
  new Response(JSON.stringify(data), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

let lastBody: GraphJSON | null = null;

/** 假后端：按请求里的图回一份结构完整的求值结果。 */
function evaluateStub(body: GraphJSON): EvaluateResult {
  const nodes: EvaluateResult["nodes"] = {};
  for (const n of body.nodes) {
    const ok = n.type !== "calc" || !/\+$/.test(String(n.fields.expr ?? ""));
    nodes[n.id] = {
      type: n.type,
      title: n.type,
      factor: null,
      values: ok ? { noncrit: 2000, crit: 4000, expected: 3000 } : null,
      isTriple: ok,
      display: ok ? "未暴击 2000.00 ｜ 暴击 4000.00 ｜ 期望 3000.00" : "",
      error: ok ? null : "表达式语法错误",
      rows: n.type === "vartable" ? [["攻击力", "1000"]] : null,
      varsText: n.type === "var" ? "变量: 攻击力=1000" : null,
      boundNames: [],
      plain: "2000",
      plainTriple: ["2000", "4000", "3000"],
    };
  }
  const resultNode = body.nodes.find((n) => n.type === "result");
  const ok = Boolean(resultNode) && !body.nodes.some((n) => nodes[n.id].error);
  return {
    ok,
    error: resultNode ? null : "没有「结果」卡片",
    result: ok && resultNode
      ? {
          nodeId: resultNode.id,
          values: { noncrit: 2000, crit: 4000, expected: 3000 },
          display: "未暴击 2000.00 ｜ 暴击 4000.00 ｜ 期望 3000.00",
          boundNames: [],
        }
      : null,
    variables: [],
    nodes,
    chainTypes: [],
    warnings: resultNode ? [] : ["没有「结果」卡片：请加一张 ★结果 卡片并把链条接到它上面"],
  };
}

function installFetch() {
  lastBody = null;
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/api/schema")) return jsonResponse(schema);
    if (url.includes("/api/help"))
      return jsonResponse({
        text: "【基本概念】\n· 每张卡片 = 一个乘区节点",
        sections: ["基本概念"],
      });
    if (url.includes("/api/evaluate")) {
      const body = JSON.parse(String(init?.body ?? "{}")) as GraphJSON;
      lastBody = body;
      return jsonResponse(evaluateStub(body));
    }
    if (url.includes("/api/report"))
      return jsonResponse({ ok: true, text: "报告正文", filename: "直伤伤害_1.txt" });
    return new Response("not found", { status: 404 });
  }) as unknown as typeof fetch;
}

async function renderApp() {
  render(<App />);
  await screen.findByTestId("sidebar");
}

const addCard = async (user: ReturnType<typeof userEvent.setup>, type: string) => {
  await user.click(screen.getByTestId(`add-${type}`));
};

describe("App 集成（假后端 + 真 schema）", () => {
  beforeEach(() => {
    window.localStorage.clear();
    installFetch();
    mockedDownload.mockClear();
    mockedPick.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("按后端 schema 渲染左侧菜单分组与预设", async () => {
    await renderApp();

    expect(screen.getByText("直伤乘区")).toBeInTheDocument();
    expect(screen.getByText("星月部件")).toBeInTheDocument();
    expect(screen.getByText("工具")).toBeInTheDocument();
    expect(screen.getByTestId("add-dmg")).toHaveTextContent("增伤区");
    expect(screen.getByTestId("add-star_coeff")).toHaveTextContent("星超导系数");
    expect(screen.getByTestId("preset-普通直伤")).toBeInTheDocument();
    expect(screen.getByTestId("preset-星·超导")).toBeInTheDocument();
  });

  it("空画布给出引导语", async () => {
    await renderApp();
    expect(screen.getByText("画布是空的")).toBeInTheDocument();
  });

  it("点菜单加卡片：卡片出现，字段与默认值一致，并显示后端算出的输出", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "dmg");

    const card = await screen.findByTestId("card-n1");
    expect(card).toHaveAttribute("data-type", "dmg");
    expect(within(card).getByDisplayValue("46.6")).toBeInTheDocument();

    await waitFor(() =>
      expect(within(card).getByText(/未暴击 2000.00/)).toBeInTheDocument(),
    );
    expect(lastBody?.nodes).toHaveLength(1);
    expect(lastBody?.nodes[0]).toMatchObject({ id: "n1", type: "dmg", inputs: 1 });
  });

  it("改字段会把新值发给后端重算（防抖后）", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "dmg");
    const input = await screen.findByDisplayValue("46.6");

    await user.clear(input);
    await user.type(input, "70+30");

    await waitFor(() => expect(lastBody?.nodes[0].fields.dmg_net).toBe("70+30"));
  });

  it("勾选框字段以布尔值发送", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "amp");
    const check = await screen.findByLabelText("命中护盾(不计)");

    await user.click(check);
    await waitFor(() => expect(lastBody?.nodes[0].fields.shield).toBe(true));
  });

  it("下拉框字段（配方）可选其它选项", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "amp");
    const select = await screen.findByRole("combobox");

    await user.selectOptions(select, "蒸发·水打火 ×2.0");
    await waitFor(() =>
      expect(lastBody?.nodes[0].fields.formula).toBe("蒸发·水打火 ×2.0"),
    );
  });

  it("一键预设：卡片数量与预设一致，且自动连成一条链、不含结果卡片", async () => {
    const user = userEvent.setup();
    await renderApp();
    await user.click(screen.getByTestId("preset-普通直伤"));

    const expected = schema.presets["普通直伤"];
    await waitFor(() => expect(lastBody?.nodes).toHaveLength(expected.length));
    expect(lastBody?.nodes.map((n) => n.type)).toEqual(expected.map((i) => i.type));
    expect(lastBody?.links).toHaveLength(expected.length - 1);
    expect(lastBody?.links[0]).toEqual({ src: "n1", dst: "n2", port: 0 });
    expect(lastBody?.nodes.some((n) => n.type === "result")).toBe(false);
  });

  it("★结果 卡片右键设置三元组变量，并保留在求值载荷里", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "result");

    const card = await screen.findByTestId("card-n1");
    fireEvent.contextMenu(within(card).getByText("★ 结果"));

    const menu = await screen.findByTestId("ctx-result");
    await user.click(within(menu).getByRole("button", { name: "设置结果变量…" }));

    const dialog = await screen.findByTestId("result-vars-dialog");
    await user.type(within(dialog).getByTestId("var-var_ex"), "期望伤害");
    await user.click(within(dialog).getByRole("button", { name: "确定" }));

    await waitFor(() => expect(lastBody?.nodes[0].fields.var_ex).toBe("期望伤害"));
    expect(screen.queryByTestId("result-vars-dialog")).not.toBeInTheDocument();
  });

  it("右键菜单可清除结果变量", async () => {
    const user = userEvent.setup();
    await renderApp();
    window.localStorage.clear();
    await addCard(user, "result");
    const card = await screen.findByTestId("card-n1");

    fireEvent.contextMenu(within(card).getByText("★ 结果"));
    await user.click(
      within(await screen.findByTestId("ctx-result")).getByRole("button", {
        name: "设置结果变量…",
      }),
    );
    const dialog = await screen.findByTestId("result-vars-dialog");
    await user.type(within(dialog).getByTestId("var-var_nc"), "未暴击伤害");
    await user.click(within(dialog).getByRole("button", { name: "确定" }));
    await waitFor(() => expect(lastBody?.nodes[0].fields.var_nc).toBe("未暴击伤害"));

    fireEvent.contextMenu(within(card).getByText("★ 结果"));
    await user.click(
      within(await screen.findByTestId("ctx-result")).getByRole("button", {
        name: "清除结果变量",
      }),
    );
    await waitFor(() => expect(lastBody?.nodes[0].fields.var_nc).toBe(""));
  });

  it("只有标题栏能拖动：dragHandle 选择器能匹配到标题栏，按钮不触发拖动", async () => {
    const user = userEvent.setup();
    await renderApp();
    await user.click(screen.getByTestId("preset-普通直伤"));
    const card = await screen.findByTestId("card-n1");

    // dragHandle 是 CSS 选择器：改错类名会让卡片彻底拖不动，所以这里要守住它能匹配到
    expect(card.querySelector(CARD_DRAG_HANDLE)).toBe(card.querySelector(".card-head"));
    expect(card.querySelector(CARD_DRAG_HANDLE)).not.toBeNull();
    // 标题栏里的按钮标了 nodrag：点 ✕ / ＋ 不会顺手把卡片拖走
    expect(within(card).getByTitle("删除卡片")).toHaveClass("nodrag");

    await addCard(user, "add");
    const plusButton = await screen.findByTitle(/增加一个输入端口/);
    expect(plusButton).toHaveClass("nodrag");
    expect(plusButton.closest(CARD_DRAG_HANDLE)).not.toBeNull(); // 按钮在标题栏里，但标了 nodrag
  });

  it("✕ 删除卡片会同时清掉相关连线", async () => {
    const user = userEvent.setup();
    await renderApp();
    await user.click(screen.getByTestId("preset-普通直伤"));
    await waitFor(() => expect(lastBody?.links.length).toBeGreaterThan(0));

    const card = await screen.findByTestId("card-n2");
    await user.click(within(card).getByTitle("删除卡片"));

    await waitFor(() => expect(lastBody?.nodes.some((n) => n.id === "n2")).toBe(false));
    expect(lastBody?.links.every((l) => l.src !== "n2" && l.dst !== "n2")).toBe(true);
  });

  it("撤销 / 重做（Ctrl+Z、Ctrl+Shift+Z）", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "dmg");
    await screen.findByTestId("card-n1");

    await user.keyboard("{Control>}z{/Control}");
    await waitFor(() => expect(screen.queryByTestId("card-n1")).not.toBeInTheDocument());

    await user.keyboard("{Control>}{Shift>}z{/Shift}{/Control}");
    await waitFor(() => expect(screen.getByTestId("card-n1")).toBeInTheDocument());
  });

  it("未保存标记：初始已保存，改动后未保存，导出工程后恢复已保存", async () => {
    const user = userEvent.setup();
    await renderApp();
    expect(screen.getByTestId("status")).toBeInTheDocument();
    expect(screen.getByText("○ 已保存")).toBeInTheDocument();

    await addCard(user, "dmg");
    await waitFor(() => expect(screen.getByText("● 未保存")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "保存工程…" }));
    await waitFor(() => expect(screen.getByText("○ 已保存")).toBeInTheDocument());
    expect(mockedDownload).toHaveBeenCalled();
  });

  it("保存工程导出的 JSON 与后端工程格式一致", async () => {
    const user = userEvent.setup();
    await renderApp();
    await user.click(screen.getByTestId("preset-剧变反应"));
    await user.click(screen.getByRole("button", { name: "保存工程…" }));

    const [filename, text] = mockedDownload.mock.calls.at(-1) as [string, string];
    expect(filename).toBe("伤害工程.json");
    const parsed = JSON.parse(text) as GraphJSON;
    expect(parsed.app).toBe("GenshinDamageCalc");
    expect(parsed.version).toBe(1);
    expect(parsed.nodes).toHaveLength(schema.presets["剧变反应"].length);
    expect(parsed.nodes[0]).toHaveProperty("pos");
    expect(parsed.links.length).toBeGreaterThan(0);
  });

  it("导出结果调用 /api/report 并下载返回的文本", async () => {
    const user = userEvent.setup();
    await renderApp();
    await user.click(screen.getByRole("button", { name: "导出结果…" }));

    await waitFor(() => expect(mockedDownload).toHaveBeenCalledWith("直伤伤害_1.txt", "报告正文"));
  });

  it("F1 打开教程并显示后端返回的文本", async () => {
    const user = userEvent.setup();
    await renderApp();
    await user.keyboard("{F1}");

    const dialog = await screen.findByTestId("help-dialog");
    expect(dialog).toHaveTextContent("基本概念");
    await user.click(within(dialog).getByRole("button", { name: "关闭 (Esc)" }));
    expect(screen.queryByTestId("help-dialog")).not.toBeInTheDocument();
  });

  it("改动会写入 localStorage（刷新不丢）", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "crit");

    await waitFor(
      () => {
        const raw = window.localStorage.getItem("genshin-dmg-calc:project:v1");
        expect(raw).toBeTruthy();
        expect(JSON.parse(raw as string).graph.nodes[0].type).toBe("crit");
      },
      { timeout: 2000 },
    );
  });

  it("启动时从 localStorage 恢复工程", async () => {
    window.localStorage.setItem(
      "genshin-dmg-calc:project:v1",
      JSON.stringify({
        graph: {
          version: 1,
          app: "GenshinDamageCalc",
          zoom: 1,
          name: "上次的工程",
          nodes: [
            { id: "n1", type: "base", pos: [40, 60], size: null, font_size: null, inputs: 0, fields: { stat_base: "1200", multiplier: "150" } },
          ],
          links: [],
        },
      }),
    );
    await renderApp();

    expect(await screen.findByTestId("card-n1")).toBeInTheDocument();
    expect(screen.getByTestId("project-name")).toHaveValue("上次的工程");
    expect(screen.getByDisplayValue("1200")).toBeInTheDocument();
  });

  it("存档里的卡片尺寸会真正落到节点容器上（宽高都要生效）", async () => {
    window.localStorage.setItem(
      "genshin-dmg-calc:project:v1",
      JSON.stringify({
        graph: {
          version: 1,
          app: "GenshinDamageCalc",
          zoom: 1,
          name: "带尺寸的工程",
          nodes: [
            {
              id: "n1",
              type: "text",
              pos: [40, 60],
              size: [320, 220],
              font_size: null,
              inputs: 0,
              fields: { content: "便签" },
            },
          ],
          links: [],
        },
      }),
    );
    await renderApp();

    const card = await screen.findByTestId("card-n1");
    const wrapper = card.parentElement as HTMLElement;
    expect(wrapper.style.width).toBe("320px");
    expect(wrapper.style.height).toBe("220px");
  });

  it("计算结果中的警告会显示在顶部状态栏", async () => {
    await renderApp();
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("没有「结果」卡片"),
    );
  });

  it("计算卡的错误会显示在卡片底部", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "calc");
    const expr = await screen.findByDisplayValue("1+1");

    await user.clear(expr);
    await user.type(expr, "1+");
    await waitFor(() =>
      expect(screen.getByTestId("card-n1")).toHaveTextContent("错误(表达式语法错误)"),
    );
  });

  it("文本卡片是便签样式：不显示字段标签、输入框无边框，且仍可编辑", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "text");

    const card = await screen.findByTestId("card-n1");
    // 字段标签「内容」不再显示（这正是原来那层多余边框的来源）
    expect(within(card).queryByText("内容")).not.toBeInTheDocument();
    // 标题栏仍在，拖动/删除的入口不变
    expect(within(card).getByText("文本")).toBeInTheDocument();
    expect(within(card).getByTitle("删除卡片")).toBeInTheDocument();

    const area = within(card).getByRole("textbox");
    expect(area.tagName).toBe("TEXTAREA");
    expect(area).toHaveClass("f-bare");

    await user.type(area, "便签内容");
    await waitFor(() => expect(lastBody?.nodes[0].fields.content).toContain("便签内容"));
  });

  it("变量表卡片显示后端返回的行", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "vartable");

    const card = await screen.findByTestId("card-n1");
    await waitFor(() => expect(within(card).getByText("攻击力")).toBeInTheDocument());
    expect(within(card).getByText("1000")).toBeInTheDocument();
  });

  it("理想圣遗物卡片渲染静态参考表（来自 schema）", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "const");

    const card = await screen.findByTestId("card-n1");
    expect(within(card).getByText("强化区间")).toBeInTheDocument();
    expect(within(card).getByText("暴击率（%）")).toBeInTheDocument();
  });
});
