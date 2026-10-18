/**
 * 端到端（jsdom）集成测试：真实 App + 真实 schema，只把后端 fetch 换成本地假实现。
 *
 * 覆盖：schema 驱动渲染、加卡片、改字段触发重算、预设、删除、撤销/重做、
 * 结果变量弹窗、一键保存 / 打开工程（走后端写文件）、未保存标记、F1 教程、
 * localStorage 自动保存。
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { CARD_DRAG_HANDLE, ROLE_H, ROLE_W } from "./model";
import type { EvaluateResult, GraphJSON, Schema } from "./types";
import fixture from "./test/schema.fixture.json";

const schema = fixture as unknown as Schema;

/** 假后端的落地目录与「打开工程」返回内容（用例里可改） */
const fakeBackend = {
  dir: "E:\\WorkStation\\GI\\DpsCalculate\\private\\projects",
  open: null as null | { ok: boolean; cancelled?: boolean; graph?: GraphJSON; dir?: string; path?: string },
  reportPath: "",
  savePath: "",
  /** /api/health 报的“前端产物过期”状态 */
  webStale: false,
  /** 模拟旧后端：/api/schema 缺字段（用来验证界面不会白屏） */
  schemaOverride: null as Schema | null,
  /** 需要指定教程内容时用它（默认给一节「基本概念」） */
  helpOverride: null as null | { text: string; sections: string[] },
  /** 需要模拟后端告警（如外部域互相引用）时给它 */
  warnings: null as string[] | null,
};

const jsonResponse = (data: unknown) =>
  new Response(JSON.stringify(data), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

let lastBody: GraphJSON | null = null;
/** 保存/导出请求的载荷（一键保存与导出结果共用） */
let savedBody: GraphJSON | null = null;

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
      // 假数据：base 卡标成「含面板 + 含拐」，用来测卡片上的可见标注
      // （真实判定在后端，见 test_role_namespace.py）
      panelFields: n.type === "base" ? ["白值"] : [],
      buffed: n.type === "base",
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
    variables: body.nodes
      .filter((n) => n.type === "role")
      .map((n) => ({
        // 假数据：每个角色都"定义了 atk"，用来验证画布上那块面板的显示与筛选
        name: `${String(n.fields.role_name ?? "").trim()}::atk`,
        value: 1000,
        text: "1000",
      })),
    nodes,
    chainTypes: [],
    warnings: fakeBackend.warnings ?? (resultNode
      ? []
      : ["没有「结果」卡片：请加一张 ★结果 卡片并把链条接到它上面"]),
    // 「角色面板」弹窗要用的拐力统计（固定造一份：辅助把 攻击%40 拐给火神）
    buffStats: {
      辅助: { out: [{ macro: "atk_pct", label: "攻击%", value: 40, role: "火神" }], in: [] },
      火神: { out: [], in: [{ macro: "atk_pct", label: "攻击%", value: 40, role: "辅助" }] },
    },
  };
}

function installFetch() {
  lastBody = null;
  savedBody = null;
  fakeBackend.reportPath = `${fakeBackend.dir}\\雷神_20261010_120000.txt`;
  fakeBackend.savePath = `${fakeBackend.dir}\\雷神.json`;
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/api/health"))
      return jsonResponse({
        ok: true,
        version: "0.1.0",
        webBuilt: true,
        webStale: fakeBackend.webStale,
        webBuildTime: "2026-10-10 01:30:20",
        webSourceTime: "2026-10-10 01:29:55",
        webReason: fakeBackend.webStale ? "前端源码比构建产物新" : "产物是最新的",
      });
    if (url.includes("/api/schema")) return jsonResponse(fakeBackend.schemaOverride ?? schema);
    if (url.includes("/api/help"))
      return jsonResponse(
        fakeBackend.helpOverride ?? {
          text: "【基本概念】\n· 每张卡片 = 一个乘区节点",
          sections: ["基本概念"],
        },
      );
    if (url.includes("/api/storage"))
      return jsonResponse({
        dir: fakeBackend.dir,
        defaultDir: fakeBackend.dir,
        configFile: "private/save_config.json",
        exists: true,
      });
    if (url.includes("/api/save/project")) {
      savedBody = JSON.parse(String(init?.body ?? "{}")) as GraphJSON;
      return jsonResponse({
        ok: true,
        path: fakeBackend.savePath,
        dir: fakeBackend.dir,
        filename: "雷神.json",
      });
    }
    if (url.includes("/api/open")) {
      return jsonResponse(
        fakeBackend.open ?? { ok: false, cancelled: true },
      );
    }
    if (url.includes("/api/report")) {
      savedBody = JSON.parse(String(init?.body ?? "{}")) as GraphJSON;
      return jsonResponse({
        ok: true,
        path: fakeBackend.reportPath,
        dir: fakeBackend.dir,
        filename: "雷神_20261010_120000.txt",
        text: "报告正文",
      });
    }
    if (url.includes("/api/evaluate")) {
      const body = JSON.parse(String(init?.body ?? "{}")) as GraphJSON;
      lastBody = body;
      return jsonResponse(evaluateStub(body));
    }
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
    // 假剪贴板也要清：粘贴现在优先读系统剪贴板，用例之间不能串
    (globalThis as unknown as { __clearFakeClipboard?: () => void }).__clearFakeClipboard?.();
    fakeBackend.open = null;
    fakeBackend.webStale = false;
    fakeBackend.schemaOverride = null;
    fakeBackend.helpOverride = null;
    fakeBackend.warnings = null;
    installFetch();
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

  it("只有标题栏能拖动：dragHandle 选择器能匹配到标题栏，删除按钮不触发拖动", async () => {
    const user = userEvent.setup();
    await renderApp();
    await user.click(screen.getByTestId("preset-普通直伤"));
    const card = await screen.findByTestId("card-n1");

    // dragHandle 是 CSS 选择器：改错类名会让卡片彻底拖不动，所以这里要守住它能匹配到
    expect(card.querySelector(CARD_DRAG_HANDLE)).toBe(card.querySelector(".card-head"));
    expect(card.querySelector(CARD_DRAG_HANDLE)).not.toBeNull();
    // 标题栏里的 ✕ 标了 nodrag：点它不会顺手把卡片拖走
    expect(within(card).getByTitle("删除卡片")).toHaveClass("nodrag");
  });

  it("加法合并卡固定 2 路输入：没有 ＋ 按钮，端口数也不是可变的", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "add");

    const card = await screen.findByTestId("card-n1");
    expect(within(card).queryByTitle(/增加一个输入端口/)).not.toBeInTheDocument();

    await waitFor(() => expect(lastBody?.nodes[0].inputs).toBe(2));
    const wrapper = card.parentElement as HTMLElement;
    expect(wrapper.querySelectorAll(".react-flow__handle.port-in")).toHaveLength(2);
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

  it("右键标题栏可折叠卡片：只显示卡片类型；折叠状态进工程 JSON，不进求值载荷", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "dmg");
    const card = await screen.findByTestId("card-n1");
    await waitFor(() => expect(lastBody?.nodes).toHaveLength(1));
    expect(within(card).getByText("增伤区净%")).toBeInTheDocument();

    fireEvent.contextMenu(card.querySelector(".card-head") as HTMLElement);
    await user.click(
      within(await screen.findByTestId("ctx-card")).getByRole("button", { name: "折叠卡片" }),
    );

    await waitFor(() => expect(card).toHaveAttribute("data-collapsed", "1"));
    // 折叠后：字段区与底部输出都不渲染，只剩卡片类型名
    expect(within(card).queryByText("增伤区净%")).not.toBeInTheDocument();
    expect(card.querySelector(".card-body")).toBeNull();
    expect(card.querySelector(".card-foot")).toBeNull();
    expect(card.textContent).toContain("增伤区");
    // 界面状态：不进求值载荷（否则折叠一次就要重算）
    expect(lastBody?.nodes[0]).not.toHaveProperty("collapsed");

    // 折叠状态随工程 JSON 保存 / 恢复
    await user.click(screen.getByRole("button", { name: "保存工程…" }));
    await waitFor(() => expect(savedBody?.nodes[0].collapsed).toBe(true));

    // 再右键可展开
    fireEvent.contextMenu(card.querySelector(".card-head") as HTMLElement);
    await user.click(
      within(await screen.findByTestId("ctx-card")).getByRole("button", { name: "展开卡片" }),
    );
    await waitFor(() => expect(card).not.toHaveAttribute("data-collapsed"));
    expect(within(card).getByText("增伤区净%")).toBeInTheDocument();
  });

  it("赋值变量卡片是纯汇点：只有输入端口，默认取「期望」", async () => {
    const user = userEvent.setup();
    await renderApp();
    expect(screen.getByTestId("add-setvar")).toHaveTextContent("赋值变量");

    await addCard(user, "setvar");
    const card = await screen.findByTestId("card-n1");

    // sink 卡片不画输出端口（schema 的 sink 字段驱动），但有输入端口
    const wrapper = card.parentElement as HTMLElement;
    expect(wrapper.querySelectorAll(".react-flow__handle.port-in")).toHaveLength(1);
    expect(wrapper.querySelectorAll(".react-flow__handle.port-out")).toHaveLength(0);

    // 字段值原样发给后端（变量名 + 取值，默认「期望」）
    await waitFor(() => expect(lastBody?.nodes[0].fields.pick).toBe("期望"));
    expect(lastBody?.nodes[0].fields).toHaveProperty("var_name");
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

  it("未保存标记：初始已保存，改动后未保存，一键保存后恢复已保存", async () => {
    const user = userEvent.setup();
    await renderApp();
    expect(screen.getByTestId("status")).toBeInTheDocument();
    expect(screen.getByText("○ 已保存")).toBeInTheDocument();

    await addCard(user, "dmg");
    await waitFor(() => expect(screen.getByText("● 未保存")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "保存工程…" }));
    await waitFor(() => expect(screen.getByText("○ 已保存")).toBeInTheDocument());
  });

  it("一键保存把工程 JSON 交给后端写文件（不再走浏览器下载）", async () => {
    const user = userEvent.setup();
    await renderApp();
    await user.click(screen.getByTestId("preset-剧变反应"));
    await user.click(screen.getByRole("button", { name: "保存工程…" }));

    await waitFor(() => expect(savedBody).not.toBeNull());
    const sent = savedBody as unknown as GraphJSON;
    expect(sent.app).toBe("GenshinDamageCalc");
    expect(sent.version).toBe(1);
    expect(sent.nodes).toHaveLength(schema.presets["剧变反应"].length);
    expect(sent.nodes[0]).toHaveProperty("pos");
    expect(sent.links.length).toBeGreaterThan(0);

    // 落地路径以提示形式给出，方便确认「存哪了」
    await waitFor(() =>
      expect(screen.getByText(new RegExp("已保存到"))).toHaveTextContent("雷神.json"),
    );
  });

  it("工具栏显示后端记住的保存目录", async () => {
    await renderApp();
    await waitFor(() =>
      expect(screen.getByTestId("save-dir")).toHaveTextContent("private\\projects"),
    );
  });

  it("后端报告前端产物过期时，工具栏给出重建提示", async () => {
    fakeBackend.webStale = true;
    await renderApp();

    const hint = await screen.findByTestId("stale-hint");
    expect(hint).toHaveTextContent("前端产物过期");
    expect(hint.getAttribute("title")).toContain("pnpm build");
  });

  it("产物是最新时不显示过期提示", async () => {
    await renderApp();
    await waitFor(() => expect(screen.getByTestId("save-dir")).toBeInTheDocument());
    expect(screen.queryByTestId("stale-hint")).not.toBeInTheDocument();
  });

  it("状态区显示前端产物构建时间（用来确认浏览器加载的是不是最新包）", async () => {
    await renderApp();
    await waitFor(() =>
      expect(screen.getByTestId("build-time")).toHaveTextContent("构建 10-10 01:30"),
    );
  });

  it("导出结果由后端写成 txt，并显示落地路径", async () => {
    const user = userEvent.setup();
    await renderApp();
    await user.click(screen.getByRole("button", { name: "导出结果…" }));

    await waitFor(() =>
      expect(screen.getByText(/已导出报告/)).toHaveTextContent("雷神_20261010_120000.txt"),
    );
    expect(savedBody).not.toBeNull();
  });

  it("打开工程走后端原生对话框：载入卡片并记住所在目录", async () => {
    const user = userEvent.setup();
    const opened = {
      ok: true,
      path: "E:\\别处\\旧工程.json",
      dir: "E:\\别处",
      graph: {
        version: 1,
        app: "GenshinDamageCalc",
        zoom: 1,
        name: "旧工程",
        nodes: [
          {
            id: "n1",
            type: "base",
            pos: [40, 60],
            size: null,
            font_size: null,
            inputs: 0,
            fields: { stat_base: "1200", multiplier: "150" },
          },
        ],
        links: [],
      } as GraphJSON,
    };
    fakeBackend.open = opened;

    await renderApp();
    await user.click(screen.getByRole("button", { name: "打开工程…" }));

    // 工程名以**文件名**为准（用户要求）：这里故意让文件里的 name 与文件名不同
    await waitFor(() => expect(screen.getByTestId("project-name")).toHaveValue("旧工程"));
    expect(await screen.findByTestId("card-n1")).toBeInTheDocument();
    expect(screen.getByTestId("save-dir")).toHaveTextContent("E:\\别处");
  });

  it("打开工程时工程名同步成文件名（文件里的 name 不同也以文件名为准）", async () => {
    const user = userEvent.setup();
    fakeBackend.open = {
      ok: true,
      path: "E:\\别处\\米c0.json",
      dir: "E:\\别处",
      graph: {
        version: 1,
        app: "GenshinDamageCalc",
        zoom: 1,
        name: "米奥瓦砂",                       // 文件里写的旧名字
        nodes: [],
        links: [],
      } as GraphJSON,
    };

    await renderApp();
    await user.click(screen.getByRole("button", { name: "打开工程…" }));

    await waitFor(() =>
      expect(screen.getByTestId("project-name")).toHaveValue("米c0"),
    );
  });

  it("打开工程被取消时静默处理（不报错、不改画布）", async () => {
    const user = userEvent.setup();
    fakeBackend.open = { ok: false, cancelled: true };
    await renderApp();

    await user.click(screen.getByRole("button", { name: "打开工程…" }));
    await waitFor(() => expect(screen.queryByText(/打开失败/)).not.toBeInTheDocument());
    expect(screen.getByText("画布是空的")).toBeInTheDocument();
  });

  it("F1 打开教程并显示后端返回的文本，章节导航可点", async () => {
    const user = userEvent.setup();
    // 假后端给两节，好验证"点第二节"这条路
    fakeBackend.helpOverride = {
      text: "【基本概念】\n· 每张卡片 = 一个乘区节点\n\n【变量】\n· 变量 = 名字 = 表达式",
      sections: ["基本概念", "变量"],
    };
    await renderApp();
    await user.keyboard("{F1}");

    const dialog = await screen.findByTestId("help-dialog");
    expect(dialog).toHaveTextContent("基本概念");
    // 顶部那排章节名是真按钮（点一下跳到那一节）；教程长，没有导航很难读
    const nav = within(dialog).getByTestId("help-nav-变量");
    expect(nav.tagName).toBe("BUTTON");
    await user.click(nav);                       // 跳转本身不该抛错 / 关掉弹窗
    expect(screen.getByTestId("help-dialog")).toBeInTheDocument();
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

  it("变量卡片是便签式文本框：不显示「定义」标签，文本框随卡片铺满", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "var");

    const card = await screen.findByTestId("card-n1");
    // 「定义」标签不再显示（原来它占掉左侧一整列，文本框铺不满）
    expect(within(card).queryByText("定义")).not.toBeInTheDocument();
    expect(within(card).getByText("变量")).toBeInTheDocument();      // 标题栏还在

    const area = within(card).getByRole("textbox");
    expect(area.tagName).toBe("TEXTAREA");
    // f-bare：无边框、铺满、且没有自己的纵向拖拽手柄（见 styles.css）
    expect(area).toHaveClass("f-bare");
    expect(area).not.toHaveAttribute("rows");

    await user.type(area, "\n秒伤 = 100");
    await waitFor(() => expect(lastBody?.nodes[0].fields.defs).toContain("秒伤 = 100"));
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

  it("理想圣遗物卡片只有表格，没有多行文本框（用户要求去掉那个控件）", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "const");

    const card = await screen.findByTestId("card-n1");
    expect(within(card).queryAllByRole("textbox")).toHaveLength(0);
    expect(within(card).getByTestId("table-relic-n1")).toBeInTheDocument();
    // 工程里也不该再存 content 字段，只剩「卡片名」这个隐藏字段（默认空）
    await waitFor(() => expect(lastBody?.nodes[0].fields).toEqual({ card_name: "" }));
  });

  it("水印显示工程名，并与工程名输入框实时同步", async () => {
    const user = userEvent.setup();
    await renderApp();
    const wm = screen.getByTestId("canvas-watermark");

    // 还没命名 → 显示「未命名」（用户确认过）
    expect(wm).toHaveAttribute("data-label", "未命名");

    await user.type(screen.getByTestId("project-name"), "雷神");
    await waitFor(() => expect(wm).toHaveAttribute("data-label", "雷神"));

    // 清空后回到占位字样
    await user.clear(screen.getByTestId("project-name"));
    await waitFor(() => expect(wm).toHaveAttribute("data-label", "未命名"));
  });

  it("水印贴在画布平面上：位于 React Flow 根容器内、按视口做平移缩放、斜放", async () => {
    await renderApp();
    const wm = screen.getByTestId("canvas-watermark");

    // children 落在 .react-flow 根里（不在 viewport 内），所以层级由 z-index 决定
    expect(wm.closest(".react-flow")).not.toBeNull();
    expect(wm.closest(".react-flow__viewport")).toBeNull();

    // 平铺图案跟着视口变换：translate(x,y) scale(zoom) rotate(斜角)
    const pattern = wm.querySelector("pattern");
    const transform = pattern?.getAttribute("patternTransform") ?? "";
    expect(transform).toMatch(/^translate\(-?\d+(\.\d+)?,-?\d+(\.\d+)?\) scale\([\d.]+\) rotate\(-24\)$/);
    // 平铺间隔按画布单位给，字号也是画布单位（随缩放一起变）
    expect(pattern).toHaveAttribute("patternUnits", "userSpaceOnUse");
    expect(Number(pattern?.getAttribute("width"))).toBeGreaterThan(100);
    expect(wm.querySelector("text")).toHaveTextContent("未命名");
  });

  it("「角色」容器卡：标题栏显示自定义角色名、面板可缩放、标题里带命名空间提示", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "role");

    const card = await screen.findByTestId("card-n1");
    expect(card).toHaveAttribute("data-type", "role");
    // 面板样式 + **节点整体不吃鼠标事件**（否则光标是抓手、在面板上拖不出框选）
    expect(card).toHaveClass("card-role-box");
    expect(card.closest(".react-flow__node")).toHaveClass("node-role-box");
    // 默认名 角色1（抽象角色，名字随用户改）
    expect(within(card).getByText("角色1")).toBeInTheDocument();
    // 画布上**不再显示**那句长说明（已写进 F1 教程），区域里只留「角色名」输入框
    expect(within(card).queryByText(/这是背景标记/)).toBeNull();
    expect(within(card).queryByText(/当前 \d+ 张卡片/)).toBeNull();
    // 区域整体不吃鼠标事件（内联样式，最稳）—— 否则光标是抓手、也拖不出框选
    expect(card.closest(".react-flow__node")).toHaveStyle({ pointerEvents: "none" });
    // 角色名改到右键菜单里设置（卡面上不再有输入框）
    expect(within(card).queryByDisplayValue("角色1")).toBeNull();
    fireEvent.contextMenu(within(card).getByText("角色1"));
    await user.click(await screen.findByText("设置角色名…"));
    const dlg = await screen.findByTestId("role-name-dialog");
    fireEvent.change(within(dlg).getByTestId("role-name-input"), { target: { value: "主C" } });
    await user.click(within(dlg).getByRole("button", { name: "确定" }));
    await waitFor(() => expect(within(card).getByText("主C")).toBeInTheDocument());
  });

  it("求值载荷里每张卡都带 role 字段（默认空串），容器自身也是空串", async () => {    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "role");
    await addCard(user, "dmg");

    await waitFor(() => expect(lastBody?.nodes).toHaveLength(2));
    const byId = Object.fromEntries((lastBody?.nodes ?? []).map((n) => [n.id, n]));
    expect(byId["n1"].role).toBe(""); // 容器自己不属于任何角色
    expect(byId["n2"].role).toBe(""); // 没落在面板里
    // 容器排在 rfNodes 前面 → 画在卡片下面（React Flow 按数组顺序叠放）
    const domOrder = Array.from(document.querySelectorAll('[data-testid^="card-n"]')).map(
      (el) => el.getAttribute("data-testid"),
    );
    expect(domOrder[0]).toBe("card-n1");
  });

  it("角色卡有拐力端口：一个入度点 + 一个出度点（多来源箭头都指向同一个点）", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "role");

    const card = await screen.findByTestId("card-n1");
    // 端口是卡片的兄弟节点（NodeResizer 与 Handle 都渲染在节点容器里）
    const box = card.closest(".react-flow__node") as HTMLElement;
    // 入度**只有一个点**（用户口径：多个箭头可以往一个点指）——
    // 所以端口位置不会随来源数量变化，箭头也就不会"错位"
    const ins = [...box.querySelectorAll<HTMLElement>(".react-flow__handle.role-port-in")];
    expect(ins).toHaveLength(1);
    // 容器百分比写法；入度在 50% 左侧、出度在 50% 右侧（用户口径：50% 那条线左右各一个）
    expect(ins[0].style.left).toMatch(/%$/);
    expect(Number.parseFloat(ins[0].style.left)).toBeLessThan(50);
    const outs = [...box.querySelectorAll<HTMLElement>(".react-flow__handle.role-port-out")];
    expect(outs).toHaveLength(1);
    expect(Number.parseFloat(outs[0].style.left)).toBeGreaterThan(50);
    // 端口上写明用途（拖过去 = 上拐）
    expect(box.querySelector(".role-port-out")?.getAttribute("title")).toContain("拐力");
  });

  it("武器卡只有出度端口（只出不进），不能连入度都没有", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "weapon");

    const card = await screen.findByTestId("card-n1");
    const box = card.closest(".react-flow__node") as HTMLElement;
    // 回归：上一版把出度端口写成 `if (!isWeapon)`，结果武器一个端口都没有
    // （用户报"武器卡片的输出端口看不见"）
    expect(box.querySelectorAll(".react-flow__handle.role-port-out")).toHaveLength(1);
    // 武器是"只出不进"：不该有入度端口
    expect(box.querySelectorAll(".react-flow__handle.role-port-in")).toHaveLength(0);
    expect(box.querySelector(".role-port-out")?.getAttribute("title")).toContain("拐力");
  });

  it("角色标记下方显示「面板」：默认只列有值的项，可在弹窗里勾选控制显示哪几项", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "role");
    const card = await screen.findByTestId("card-n1");

    // 假后端说这个角色定义了 atk=1000 → 面板里就有这一行（其余宏没值，不显示）
    const panel = await screen.findByTestId("role-panel-n1");
    await waitFor(() => expect(panel).toHaveTextContent("atk"));
    expect(panel).toHaveTextContent("1000");
    expect(panel).not.toHaveTextContent("crit_rate");

    // 在「角色面板…」里勾上 crit_rate → 确定 → 写进 panel_show，画布面板按勾选显示
    fireEvent.contextMenu(within(card).getByText("角色1"));
    await user.click(await screen.findByText("角色面板…"));
    const dialog = await screen.findByTestId("role-panel-dialog");
    await user.click(within(dialog).getByTestId("panel-show-crit_rate"));
    await user.click(within(dialog).getByRole("button", { name: "确定" }));

    await waitFor(() => expect(lastBody?.nodes[0].fields.panel_show).toBe("crit_rate"));
    await waitFor(() => expect(screen.getByTestId("role-panel-n1")).toHaveTextContent("crit_rate"));
    // 勾选是白名单：没勾的 atk 不再显示
    expect(screen.getByTestId("role-panel-n1")).not.toHaveTextContent("atk ");
  });

  it("变量卡右键可切换「卡片底部是否显示算出的变量值」（默认隐藏）", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "var");
    const card = await screen.findByTestId("card-n1");

    // 默认**隐藏**（用户要求：卡片默认干净）
    await waitFor(() => expect(lastBody?.nodes[0].fields.show_vars).toBe(false));
    expect(within(card).queryByText(/变量: 攻击力=1000/)).toBeNull();

    // 右键 →「显示变量值」→ 写回 show_vars=true，底部那行出来了
    fireEvent.contextMenu(within(card).getByText("变量"));
    await user.click(await screen.findByText("显示变量值"));
    await waitFor(() => expect(lastBody?.nodes[0].fields.show_vars).toBe(true));
    await waitFor(() => expect(within(card).getByText(/变量: 攻击力=1000/)).toBeInTheDocument());

    // 再右键 → 菜单项变成「隐藏变量值」→ 点回去
    fireEvent.contextMenu(within(card).getByText("变量"));
    await user.click(await screen.findByText("隐藏变量值"));
    await waitFor(() => expect(lastBody?.nodes[0].fields.show_vars).toBe(false));
    await waitFor(() => expect(within(card).queryByText(/变量: 攻击力=1000/)).toBeNull());
  });

  it("新建的变量卡默认是一张白纸（定义框为空）", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "var");
    const card = await screen.findByTestId("card-n1");

    await waitFor(() => expect(lastBody?.nodes[0].fields.defs).toBe(""));
    const box = within(card).getByRole("textbox");
    expect(box).toHaveValue("");
  });

  it("右键角色 →「隐藏区域内的卡片」：区域内卡片与连线一起消失、容器折叠成最小", async () => {
    const user = userEvent.setup();
    // jsdom 里拖不动卡片（d3-drag 是桩），所以直接预置一份「卡片已经放在角色区域里」的工程；
    // 角色容器固定成默认尺寸 → "卡片在区域里"只由坐标决定，不受 jsdom 量不到尺寸影响
    window.localStorage.setItem(
      "genshin-dmg-calc:project:v1",
      JSON.stringify({
        graph: {
          version: 1,
          app: "GenshinDamageCalc",
          zoom: 1,
          name: "隐藏自检",
          nodes: [
            { id: "n1", type: "role", pos: [0, 0], size: [ROLE_W, ROLE_H], font_size: null, inputs: 0,
              fields: { role_name: "火神", panel: "", panel_show: "", card_name: "" } },
            { id: "n2", type: "dmg", pos: [120, 70], size: null, font_size: null, inputs: 1,
              fields: {} },
            { id: "n3", type: "crit", pos: [120, 240], size: null, font_size: null, inputs: 1,
              fields: {} },
          ],
          // 两张卡之间的伤害连线：端点在区域内 → 隐藏卡片时这条线也该消失
          links: [{ src: "n2", dst: "n3", port: 0 }],
        },
        savedAt: new Date().toISOString(),
      }),
    );

    await renderApp();
    const roleCard = await screen.findByTestId("card-n1");
    expect(screen.getByTestId("card-n2")).toBeInTheDocument();
    expect(screen.getByTestId("card-n3")).toBeInTheDocument();
    await waitFor(() => expect(lastBody?.nodes.map((n) => n.id)).toEqual(["n1", "n2", "n3"]));
    await waitFor(() => expect(document.querySelectorAll(".react-flow__edge").length).toBe(1));

    // 菜单里报出区域内的卡片数
    fireEvent.contextMenu(within(roleCard).getByText("火神"));
    const item = await screen.findByText(/隐藏区域内的卡片/);
    expect(item).toHaveTextContent("2 张");
    await user.click(item);

    // 字段写进角色卡；区域内的卡片与连线不再渲染
    await waitFor(() =>
      expect(lastBody?.nodes.find((n) => n.id === "n1")?.fields.cards_hidden).toBe(true),
    );
    await waitFor(() => expect(screen.queryByTestId("card-n2")).toBeNull());
    expect(screen.queryByTestId("card-n3")).toBeNull();
    expect(document.querySelectorAll(".react-flow__edge").length).toBe(0);
    // 只是不渲染：求值载荷里这些卡片还在（隐藏不影响计算）
    expect(lastBody?.nodes.map((n) => n.id)).toEqual(["n1", "n2", "n3"]);

    // 角色容器折叠成最小（只留一张牌子）
    expect(screen.getByTestId("card-n1")).toHaveAttribute("data-collapsed", "1");
    expect((screen.getByTestId("card-n1").closest(".react-flow__node") as HTMLElement).style.height)
      .toBe("auto");

    // 再右键 →「显示区域内的卡片」→ 卡片回来，且容器**一起展开**
    // （回归：原来只恢复卡片、容器还折着，看着像"展开后卡片没了"；
    //   折叠后标题栏仍然显示角色名，所以还能按名字找它）
    fireEvent.contextMenu(within(screen.getByTestId("card-n1")).getByText("火神"));
    await user.click(await screen.findByText(/显示区域内的卡片/));
    await waitFor(() =>
      expect(lastBody?.nodes.find((n) => n.id === "n1")?.fields.cards_hidden).toBe(false),
    );
    await waitFor(() => expect(screen.getByTestId("card-n2")).toBeInTheDocument());
    // 展开后标题栏回到角色名（折叠时显示的是卡片类型名）
    await waitFor(() => expect(within(screen.getByTestId("card-n1")).getByText("火神"))
      .toBeInTheDocument());
    expect(screen.getByTestId("card-n1")).not.toHaveAttribute("data-collapsed");
  });

  it("区域内的卡片和区域外有连线时：菜单项禁用并说明是哪张卡（不隐藏）", async () => {
    const user = userEvent.setup();
    window.localStorage.setItem(
      "genshin-dmg-calc:project:v1",
      JSON.stringify({
        graph: {
          version: 1,
          app: "GenshinDamageCalc",
          zoom: 1,
          name: "跨区连线自检",
          nodes: [
            { id: "n1", type: "role", pos: [0, 0], size: [ROLE_W, ROLE_H], font_size: null, inputs: 0,
              fields: { role_name: "火神", panel: "", panel_show: "", card_name: "" } },
            { id: "n2", type: "dmg", pos: [120, 70], size: null, font_size: null, inputs: 1,
              fields: {} },
            // 远在角色区域之外
            { id: "n3", type: "crit", pos: [900, 700], size: null, font_size: null, inputs: 1,
              fields: {} },
          ],
          links: [{ src: "n2", dst: "n3", port: 0 }],
        },
        savedAt: new Date().toISOString(),
      }),
    );

    await renderApp();
    const roleCard = await screen.findByTestId("card-n1");
    await waitFor(() => expect(lastBody?.nodes.map((n) => n.id)).toEqual(["n1", "n2", "n3"]));

    fireEvent.contextMenu(within(roleCard).getByText("火神"));
    const item = await screen.findByText(/隐藏区域内的卡片/);
    expect(item).toBeDisabled();
    // 说清是哪张卡连到外面（暴击区的中文名来自后端 schema）
    expect(item.getAttribute("title")).toContain("暴击区");

    // 点了也不会隐藏
    await user.click(item);
    expect(screen.getByTestId("card-n2")).toBeInTheDocument();
    expect(screen.getByTestId("card-n1")).not.toHaveAttribute("data-collapsed");
  });

  it("角色名不许重名：重名时当场提示并禁用「确定」，改回自己的名字可以保存", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "role");
    await addCard(user, "role");
    const first = await screen.findByTestId("card-n1");

    fireEvent.contextMenu(within(first).getByText("角色1"));
    await user.click(await screen.findByText("设置角色名…"));
    const dlg = await screen.findByTestId("role-name-dialog");
    expect(within(dlg).queryByTestId("role-name-error")).toBeNull();

    // 起一个已经存在的名字 → 红字提示 + 确定不可点
    fireEvent.change(within(dlg).getByTestId("role-name-input"), { target: { value: "角色2" } });
    const err = within(dlg).getByTestId("role-name-error");
    expect(err).toHaveTextContent("同名");
    expect(within(dlg).getByRole("button", { name: "确定" })).toBeDisabled();

    // 改成没被占用的名字 → 提示消失、可以保存
    fireEvent.change(within(dlg).getByTestId("role-name-input"), { target: { value: "火神" } });
    expect(within(dlg).queryByTestId("role-name-error")).toBeNull();
    await user.click(within(dlg).getByRole("button", { name: "确定" }));
    await waitFor(() =>
      expect(lastBody?.nodes.find((n) => n.id === "n1")?.fields.role_name).toBe("火神"),
    );
  });

  it("打开旧工程时把压在一起的角色区域挪开，并提示「未保存」", async () => {
    window.localStorage.setItem(
      "genshin-dmg-calc:project:v1",
      JSON.stringify({
        graph: {
          version: 1,
          app: "GenshinDamageCalc",
          zoom: 1,
          name: "重叠自检",
          nodes: [
            { id: "n1", type: "role", pos: [0, 0], size: [560, 380], font_size: null, inputs: 0,
              fields: { role_name: "火神", panel: "", panel_show: "", card_name: "" } },
            // 和 n1 压在一起
            { id: "n2", type: "role", pos: [100, 100], size: [560, 380], font_size: null, inputs: 0,
              fields: { role_name: "辅助", panel: "", panel_show: "", card_name: "" } },
          ],
          links: [],
        },
        savedAt: new Date().toISOString(),
      }),
    );

    await renderApp();
    // 提示：自动挪开
    await waitFor(() => expect(screen.getByText(/已自动挪开/)).toBeInTheDocument());
    // 位置被改过 → 状态变成「未保存」
    expect(screen.getByText("● 未保存")).toBeInTheDocument();
    // 求值载荷里两个角色都还在（挪动只是界面层）
    await waitFor(() => expect(lastBody?.nodes.map((n) => n.id)).toEqual(["n1", "n2"]));
  });

  it("Ctrl+C / Ctrl+V：右键「复制角色域」后粘贴，域与域内卡片一起来、撞名自动加 _2", async () => {
    const user = userEvent.setup();
    // 预置：火神域 + 域内两张卡（域外线不带走）
    window.localStorage.setItem(
      "genshin-dmg-calc:project:v1",
      JSON.stringify({
        graph: {
          version: 1, app: "GenshinDamageCalc", zoom: 1, name: "复制自检",
          nodes: [
            { id: "n1", type: "role", pos: [0, 0], size: [520, 340], font_size: null, inputs: 0,
              fields: { role_name: "火神", panel: "", panel_show: "", card_name: "" } },
            { id: "n2", type: "dmg", pos: [60, 60], size: null, font_size: null, inputs: 1, fields: {} },
            { id: "n3", type: "crit", pos: [60, 200], size: null, font_size: null, inputs: 1, fields: {} },
            { id: "n4", type: "base", pos: [3000, 0], size: null, font_size: null, inputs: 0, fields: {} },
          ],
          links: [{ src: "n2", dst: "n3", port: 0 }],
        },
        savedAt: new Date().toISOString(),
      }),
    );

    await renderApp();
    const roleCard = await screen.findByTestId("card-n1");
    await waitFor(() => expect(lastBody?.nodes.length).toBe(4));

    // 右键域 →「复制角色域」（等价于选中域后 Ctrl+C）
    fireEvent.contextMenu(within(roleCard).getByText("火神"));
    await user.click(await screen.findByText(/复制角色域/));
    // 复制是静默的（成功不弹提示），这里直接断言**系统剪贴板**里写进了 JSON 卡片包
    await waitFor(async () => {
      expect(await navigator.clipboard.readText()).toContain("GenshinDamageCalc:cards");
    });

    // Ctrl+V：粘出「火神_2」+ 域内两张卡
    fireEvent.keyDown(window, { key: "v", ctrlKey: true });
    await waitFor(() => expect(lastBody?.nodes.length).toBe(7));
    const roles = (lastBody?.nodes ?? []).filter((n) => n.type === "role");
    expect(roles.map((r) => r.fields.role_name).sort()).toEqual(["火神", "火神_2"]);
    // 域内两张卡也跟着来了（各自的 type 计数翻倍）
    const types = (lastBody?.nodes ?? []).map((n) => n.type);
    expect(types.filter((t) => t === "dmg")).toHaveLength(2);
    expect(types.filter((t) => t === "crit")).toHaveLength(2);
    // 内部那条线按新 id 接回来（总连线数 1 → 2）
    expect(lastBody?.links).toHaveLength(2);
    expect(new Set((lastBody?.nodes ?? []).map((n) => n.id)).size).toBe(7);
  });

  it("工具栏「框选域」开关：默认关，点一下变开（aria-pressed 跟着变、下方不弹提示）", async () => {
    const user = userEvent.setup();
    await renderApp();
    const btn = screen.getByTestId("box-select-domains");
    // 默认关：框选只选普通卡片（角色/武器域要单独点标题栏）
    expect(btn).toHaveAttribute("aria-pressed", "false");
    expect(btn).not.toHaveClass("on");

    await user.click(btn);
    expect(btn).toHaveAttribute("aria-pressed", "true");
    expect(btn).toHaveClass("on");
    // 用户要求：切换时不要在界面下方出提示（开关自己的高亮就是状态）
    expect(screen.queryByTestId("toast")).toBeNull();

    // 再点一次关回去
    await user.click(btn);
    expect(btn).toHaveAttribute("aria-pressed", "false");
    expect(btn).not.toHaveClass("on");
    expect(screen.queryByTestId("toast")).toBeNull();
  });

  it("右键武器域 →「设置武器名…」：弹窗标题与标签都是「武器名」", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "weapon");
    const card = await screen.findByTestId("card-n1");

    fireEvent.contextMenu(card.querySelector(".card-head") as Element);
    await user.click(await screen.findByText("设置武器名…"));
    const dlg = await screen.findByTestId("role-name-dialog");
    // 武器与角色共用这套命名空间逻辑，但字面上要区分（用户要求）
    expect(within(dlg).getByRole("heading")).toHaveTextContent("设置武器名");
    expect(within(dlg).getByText("武器名")).toBeInTheDocument();
    expect(within(dlg).queryByText("角色名")).toBeNull();
  });

  it("后端报「外部域互相引用」时在底部提示一次", async () => {
    fakeBackend.warnings = ["外部域：「a.json」与「b.json」互相引用，环上那条来源按 0 计算"];
    await renderApp();
    // 底部提示（toast）里能看到，说明用户知道某个来源被按 0 算了
    expect(
      await screen.findByText(/外部域：「a\.json」与「b\.json」互相引用/),
    ).toBeInTheDocument();
  });

it("域对照表：行列直接写在表格里（不再有底部字段），回车加一条并把光标搬过去", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "matrix");
    const card = await screen.findByTestId("card-n1");

    // 表格在；底部不再有「固定拐力」这种普通字段
    expect(within(card).getByTestId("matrix-n1")).toBeInTheDocument();
    expect(within(card).queryByText("固定拐力")).toBeNull();

    // 列 / 行各一个单行输入框；左上角是固定拐力（可多选，至少一个输入框）
    expect(within(card).getByTestId("mx-col-n1-0")).toBeInTheDocument();
    expect(within(card).getByTestId("mx-row-n1-0")).toBeInTheDocument();
    expect(within(card).getByTestId("ext-source-n1-fixed-0")).toBeInTheDocument();

    // 行里回车 → 在下面加一条，并且光标落到新加的那条上
    fireEvent.keyDown(within(card).getByTestId("mx-row-n1-0"), { key: "Enter" });
    const row1 = await within(card).findByTestId("mx-row-n1-1");
    await waitFor(() => expect(document.activeElement).toBe(row1));

    // 空行按退格 → 删掉，光标回到上一条
    fireEvent.keyDown(row1, { key: "Backspace" });
    await waitFor(() => expect(within(card).queryByTestId("mx-row-n1-1")).toBeNull());
    expect(document.activeElement).toBe(within(card).getByTestId("mx-row-n1-0"));
  });

  it("域对照表的行头能装下长文件名（输入框按内容给宽度，不截断）", async () => {
    const longName = "data/米提亚零命专武精五银钢风套三百精通满词条.json";
    window.localStorage.setItem(
      "genshin-dmg-calc:project:v1",
      JSON.stringify({
        graph: {
          version: 1,
          app: "GenshinDamageCalc",
          zoom: 1,
          name: "长路径",
          nodes: [
            {
              id: "m1",
              type: "matrix",
              pos: [40, 40],
              size: [900, 320],
              font_size: null,
              inputs: 0,
              fields: { row_files: longName, col_files: "", fixed_file: "" },
            },
          ],
          links: [],
        },
        savedAt: new Date().toISOString(),
      }),
    );
    await renderApp();
    const card = await screen.findByTestId("card-m1");
    const input = within(card).getByTestId("mx-row-m1-0") as HTMLInputElement;
    // size 至少跟文件名长度同量级（否则会被截断）
    expect(Number(input.getAttribute("size"))).toBeGreaterThan(20);
    // 悬停还能看到完整路径
    expect(input.getAttribute("title")).toBe(longName);
  });

  it("右键角色标签 →「角色面板…」：宏表可编辑、并显示拐力统计（OUT/IN）", async () => {    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "role");
    const card = await screen.findByTestId("card-n1");

    fireEvent.contextMenu(within(card).getByText("角色1"));
    await user.click(await screen.findByText("角色面板…"));

    const dialog = await screen.findByTestId("role-panel-dialog");
    // 宏表来自 schema（中文名也来自后端，不在前端硬编码）
    expect(within(dialog).getByText("攻击力")).toBeInTheDocument();
    expect(within(dialog).getByTestId("panel-atk_pct")).toBeInTheDocument();
    // 「喂给哪张卡」直接显示在行内（不是只放在 title 里）
    expect(within(dialog).getAllByText("基础值 / 属性源 → 白值").length).toBeGreaterThan(0);
    // 拐力统计（角色1 在这份假数据里没有统计 → 两栏都是「无」）
    expect(within(dialog).getAllByTestId("buff-empty").length).toBe(2);

    // 填一个宏 → 确定 → 写进角色卡的隐藏字段 panel
    fireEvent.change(within(dialog).getByTestId("panel-atk_pct"), { target: { value: "40" } });
    await user.click(within(dialog).getByRole("button", { name: "确定" }));
    await waitFor(() =>
      expect(lastBody?.nodes[0].fields.panel).toBe("atk_pct = 40"),
    );
  });

  it("角色面板弹窗能增删自定义对外项（out::名字），存进面板字段并往返稳定", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "role");
    const card = await screen.findByTestId("card-n1");

    fireEvent.contextMenu(within(card).getByText("角色1"));
    await user.click(await screen.findByText("角色面板…"));
    let dialog = await screen.findByTestId("role-panel-dialog");

    // 默认没有自定义行；点「＋」加一行（名字给个不重复的建议值）
    expect(within(dialog).queryByTestId("panel-custom-name-0")).toBeNull();
    await user.click(within(dialog).getByTestId("panel-custom-add"));
    expect(within(dialog).getByTestId("panel-custom-name-0")).toHaveValue("buff");

    // 改名 + 填值（固定宏也填一个，验证两类行一起存）
    fireEvent.change(within(dialog).getByTestId("panel-custom-name-0"), {
      target: { value: "gift" },
    });
    fireEvent.change(within(dialog).getByTestId("panel-custom-value-0"), {
      target: { value: "40" },
    });
    fireEvent.change(within(dialog).getByTestId("panel-atk_pct"), { target: { value: "20" } });
    await user.click(within(dialog).getByRole("button", { name: "确定" }));

    await waitFor(() =>
      expect(lastBody?.nodes[0].fields.panel).toBe("atk_pct = 20\nout::gift = 40"),
    );

    // 再打开：这一行还在（改名与值都没丢）
    fireEvent.contextMenu(within(card).getByText("角色1"));
    await user.click(await screen.findByText("角色面板…"));
    dialog = await screen.findByTestId("role-panel-dialog");
    expect(within(dialog).getByTestId("panel-custom-name-0")).toHaveValue("gift");
    expect(within(dialog).getByTestId("panel-custom-value-0")).toHaveValue("40");

    // 名字非法 → 就地给提示（不是静默丢掉）
    fireEvent.change(within(dialog).getByTestId("panel-custom-name-0"), {
      target: { value: "Bad" },
    });
    expect(within(dialog).getByTestId("panel-custom-hint-0")).toHaveTextContent("小写字母");

    // 删掉这一行 → 面板字段里只剩固定宏
    await user.click(within(dialog).getByTestId("panel-custom-del-0"));
    await user.click(within(dialog).getByRole("button", { name: "确定" }));
    await waitFor(() => expect(lastBody?.nodes[0].fields.panel).toBe("atk_pct = 20"));
  });

  it("角色面板弹窗在「火神」名下会显示后端给的 OUT/IN 统计", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "role");
    const card = await screen.findByTestId("card-n1");

    // 把角色名改成 火神（假后端对「火神」有统计数据）—— 现在走右键「设置角色名…」
    fireEvent.contextMenu(within(card).getByText("角色1"));
    await user.click(await screen.findByText("设置角色名…"));
    const nameDlg = await screen.findByTestId("role-name-dialog");
    fireEvent.change(within(nameDlg).getByTestId("role-name-input"), {
      target: { value: "火神" },
    });
    await user.click(within(nameDlg).getByRole("button", { name: "确定" }));

    fireEvent.contextMenu(within(card).getByText("火神"));
    await user.click(await screen.findByText("角色面板…"));

    const dialog = await screen.findByTestId("role-panel-dialog");
    // 统计来自后端 /api/evaluate（首次求值完成前是空的，所以这里等它到位）
    await waitFor(() => expect(within(dialog).getByText("辅助")).toBeInTheDocument());
    expect(within(dialog).getByText("40")).toBeInTheDocument();     // 数值
  });

  it("新建项目：先问工程名，再完整重置（画布 / 工程名 / 历史 / 本地存档）", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "dmg");
    await user.type(screen.getByTestId("project-name"), "旧工程");
    await waitFor(() => expect(screen.getByText("● 未保存")).toBeInTheDocument());

    await user.click(screen.getByTestId("new-project"));
    const dialog = await screen.findByTestId("new-project-dialog");
    // 预填当前工程名（说明文字已按用户要求删掉，这里只校验输入框）
    expect(within(dialog).getByTestId("new-project-name")).toHaveValue("旧工程");

    fireEvent.change(within(dialog).getByTestId("new-project-name"), {
      target: { value: "雷神直伤" },
    });
    await user.click(within(dialog).getByRole("button", { name: "新建" }));

    // 画布清空、工程名换成新的、状态回到"已保存"
    await waitFor(() => expect(screen.getByText("画布是空的")).toBeInTheDocument());
    expect(screen.getByTestId("project-name")).toHaveValue("雷神直伤");
    await waitFor(() => expect(screen.getByText("○ 已保存")).toBeInTheDocument());
    // 本地自动存档也跟着重置（存的是 {graph, savedAt} 包裹结构）
    await waitFor(() => {
      const saved = JSON.parse(
        window.localStorage.getItem("genshin-dmg-calc:project:v1") ?? "{}",
      ) as { graph?: { name?: string; nodes?: unknown[] } };
      expect(saved.graph?.name).toBe("雷神直伤");
      expect(saved.graph?.nodes).toEqual([]);
    });
  });

  it("新建项目弹窗可以取消（什么都不改）", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "dmg");

    await user.click(screen.getByTestId("new-project"));
    const dialog = await screen.findByTestId("new-project-dialog");
    await user.click(within(dialog).getByRole("button", { name: "取消" }));

    expect(screen.queryByTestId("new-project-dialog")).toBeNull();
    expect(screen.getByTestId("card-n1")).toBeInTheDocument();
  });

  it("旧后端（schema 缺 panelMacros）打开角色面板不再白屏，而是给出重启提示", async () => {
    const user = userEvent.setup();
    // 造一个"旧后端"：把 panelMacros 与 hidden_fields 去掉
    const old = JSON.parse(JSON.stringify(schema)) as Record<string, unknown> & {
      nodeTypes: Record<string, Record<string, unknown>>;
    };
    delete old.panelMacros;
    for (const spec of Object.values(old.nodeTypes)) {
      delete spec.hidden_fields;
    }
    fakeBackend.schemaOverride = old as unknown as Schema;

    await renderApp();
    await addCard(user, "role");
    const card = await screen.findByTestId("card-n1");

    fireEvent.contextMenu(within(card).getByText("角色1"));
    await user.click(await screen.findByText("角色面板…"));

    const dialog = await screen.findByTestId("role-panel-dialog");
    // 弹窗里的提示文字按用户要求删掉了，但「旧后端也不白屏」这条契约还要守住
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByTestId("panel-custom-add")).toBeInTheDocument();
    // 页面本身照常可用（没有白屏）
    expect(screen.getByTestId("sidebar")).toBeInTheDocument();
  });

  it("拐力端口并排在左上角标签的正上方（箭头的始末都在标签上方）", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "role");
    const card = await screen.findByTestId("card-n1");
    const box = card.closest(".react-flow__node") as HTMLElement;

    const portIn = box.querySelector(".react-flow__handle.role-port-in");
    const portOut = box.querySelector(".react-flow__handle.role-port-out");
    expect(portIn).not.toBeNull();
    expect(portOut).not.toBeNull();
    // 都用 Position.Top（连线朝上走），而不是默认的左右两边
    expect(portIn).toHaveClass("react-flow__handle-top");
    expect(portOut).toHaveClass("react-flow__handle-top");
    expect(box.querySelector(".react-flow__handle-left")).toBeNull();
    expect(box.querySelector(".react-flow__handle-right")).toBeNull();
    // 具体坐标（"在标签正上方、一进一出并排"）由 styles.css 的 .role-port-* 决定，
    // 见 styles.test.ts 的契约用例 —— jsdom 没有布局，这里只能验到行为层面
  });

  it("卡片底部标注「含面板」与「含拐」——让人一眼看出在吃面板/拐力", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "base");
    await addCard(user, "dmg");

    const base = await screen.findByTestId("card-n1");
    await waitFor(() => expect(within(base).getByTestId("panel-mark-n1")).toBeInTheDocument());
    expect(within(base).getByTestId("buff-mark-n1")).toHaveTextContent("含拐");
    // 后端没标的卡片不显示这两个标记
    const dmg = await screen.findByTestId("card-n2");
    expect(within(dmg).queryByTestId("buff-mark-n2")).toBeNull();
    expect(within(dmg).queryByTestId("panel-mark-n2")).toBeNull();
  });

  it("右键「命名卡片…」给卡片起名：标题栏挂上名字徽标，名字进工程字段", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "dmg");

    const card = await screen.findByTestId("card-n1");
    fireEvent.contextMenu(within(card).getByText("增伤区"));

    await user.click(await screen.findByText("命名卡片…"));
    const input = await screen.findByTestId("card-name-input");
    await user.type(input, "雷神增伤");
    await user.click(screen.getByRole("button", { name: "确定" }));

    // 标题仍是类型，名字另挂徽标（徽标只显示名字，不带尾随 ::）
    await waitFor(() => expect(within(card).getByText("雷神增伤")).toBeInTheDocument());
    expect(within(card).getByText("增伤区")).toBeInTheDocument();
    // 名字是隐藏字段 card_name，随载荷一起发给后端（供 卡片名::暴击 引用）
    await waitFor(() => expect(lastBody?.nodes[0].fields.card_name).toBe("雷神增伤"));
    // 名字**不占卡片版面**：卡片体里不该出现「卡片名」输入框
    expect(within(card).queryByDisplayValue("雷神增伤")).toBeNull();
  });

  it("命名后清空 = 取消命名（徽标消失，标题栏回到只有类型名）", async () => {
    const user = userEvent.setup();
    await renderApp();
    await addCard(user, "dmg");
    const card = await screen.findByTestId("card-n1");

    fireEvent.contextMenu(within(card).getByText("增伤区"));
    await user.click(await screen.findByText("命名卡片…"));
    await user.type(await screen.findByTestId("card-name-input"), "临时名");
    await user.click(screen.getByRole("button", { name: "确定" }));
    await waitFor(() => expect(within(card).getByText("临时名")).toBeInTheDocument());

    fireEvent.contextMenu(within(card).getByText("增伤区"));
    await user.click(await screen.findByText("命名卡片…"));
    await user.clear(await screen.findByTestId("card-name-input"));
    await user.click(screen.getByRole("button", { name: "确定" }));

    await waitFor(() => expect(within(card).queryByText("临时名")).toBeNull());
    expect(within(card).getByText("增伤区")).toBeInTheDocument();
  });
});
