/** 画布模型纯函数测试（落位 / 对齐 / 预设 / 工程 JSON 往返）。 */
import { describe, expect, it } from "vitest";
import {
  ROLE_H,
  ROLE_W,
  addPreset,
  alignPositions,
  areaFree,
    chainOrigin,
  connect,
  estimateSize,
  freeSlot,
  graphToJSON,
  ignoredByBoxSelect,
  jsonToGraph,
  formatPanel,
  formatPanelShow,
  parsePanel,
  parsePanelShow,
  makeNode,
  nextNodeId,
  nextRoleName,
  normalizeSchema,
  panelPreset,
  needsPanelPreset,
  fillPresetForDropped,
  isNamespaceNode,
  isPanelNode,
  buildRoleMap,
  roleBoxes,
  roleOfNode,
  spreadChain,
  validRoleName,
  validCustomOut,
  nextCustomOutName,
  parseRolePanel,
  formatRolePanel,
  wouldCycle,
} from "./model";
import type { CardNode, GraphJSON, Schema } from "./types";
import fixture from "./test/schema.fixture.json";

const schema = fixture as unknown as Schema;

const node = (id: string, type: string, pos: [number, number], extra: Partial<CardNode> = {}) =>
  ({ ...makeNode(schema, type, pos, id), ...extra }) as CardNode;

describe("建卡与落位", () => {
  it("makeNode 用 schema 默认值，并支持覆盖", () => {
    const n = makeNode(schema, "dmg", [10, 20], "n1");
    expect(n.fields.dmg_net).toBe("46.6");
    expect(n.inputs).toBe(1);
    const o = makeNode(schema, "coeff", [0, 0], "n2", { coeff: "3" });
    expect(o.fields.coeff).toBe("3");
  });

  it("nextNodeId 递增且不重复", () => {
    expect(nextNodeId([])).toBe("n1");
    expect(nextNodeId([node("n1", "dmg", [0, 0]), node("n4", "dmg", [0, 0])])).toBe("n5");
    expect(nextNodeId([node("x7", "dmg", [0, 0])])).toBe("n1");
  });

  it("areaFree 带 20px 间距判断重叠", () => {
    const nodes = [node("n1", "dmg", [100, 100])];
    expect(areaFree(nodes, 500, 100, 300, 210)).toBe(true);
    expect(areaFree(nodes, 120, 110, 300, 210)).toBe(false);
  });

  it("freeSlot 避开已有卡片", () => {
    expect(freeSlot([])).toEqual([40, 60]);
    const taken = [node("n1", "dmg", [40, 60])];
    expect(freeSlot(taken)).not.toEqual([40, 60]);
  });

  it("chainOrigin 找空白行", () => {
    expect(chainOrigin([], 3)).toEqual([40, 120]);
    const taken = [node("n1", "dmg", [40, 120])];
    expect(chainOrigin(taken, 1)[1]).toBeGreaterThan(120);
  });
});

describe("预设", () => {
  it("普通直伤预设不含结果卡片，且首尾相连", () => {
    const res = addPreset(schema, "普通直伤", [], [], estimateSize);
    const types = res.nodes.map((n) => n.type);
    expect(types).toContain("base");
    expect(types).not.toContain("result");
    expect(res.links).toHaveLength(res.nodes.length - 1);
    expect(res.links[0]).toMatchObject({ src: "n1", dst: "n2", port: 0 });
  });

  it("预设字段覆盖生效（月·直伤 的系数为 3）", () => {
    const res = addPreset(schema, "月·直伤", [], [], estimateSize);
    const coeff = res.nodes.find((n) => n.type === "coeff");
    expect(coeff?.fields.coeff).toBe("3");
  });

  it("预设追加在已有卡片下方，不重叠", () => {
    const first = addPreset(schema, "普通直伤", [], [], estimateSize);
    const second = addPreset(schema, "剧变反应", first.nodes, first.links, estimateSize);
    const added = second.nodes.slice(first.nodes.length);
    const lastY = Math.max(...first.nodes.map((n) => n.pos[1]));
    const firstNewY = Math.min(...added.map((n) => n.pos[1]));

    expect(second.nodes).toHaveLength(first.nodes.length + added.length);
    expect(added.length).toBe(schema.presets["剧变反应"].length);
    expect(firstNewY).toBeGreaterThan(lastY);
    // 已有卡片位置不动
    expect(second.nodes.slice(0, first.nodes.length)).toEqual(first.nodes);
  });

  it("未知预设安全返回", () => {
    const res = addPreset(schema, "不存在", [], [], estimateSize);
    expect(res.created).toEqual([]);
    expect(res.nodes).toEqual([]);
  });

  it("spreadChain 按真实宽度排开", () => {
    const nodes = [
      node("n1", "dmg", [0, 0], { measured: { width: 500, height: 200 } }),
      node("n2", "dmg", [0, 0]),
    ];
    const out = spreadChain(nodes, ["n1", "n2"], 300, estimateSize);
    expect(out[0].pos).toEqual([0, 300]);
    expect(out[1].pos).toEqual([540, 300]); // 500 + 40
  });
});

describe("对齐", () => {
  const nodes = [
    node("n1", "dmg", [0, 0], { measured: { width: 100, height: 100 } }),
    node("n2", "dmg", [300, 200], { measured: { width: 200, height: 100 } }),
  ];

  it("左对齐 / 顶对齐取最小边", () => {
    expect(alignPositions(nodes, ["n1", "n2"], "left")).toEqual({
      n1: [0, 0],
      n2: [0, 200],
    });
    expect(alignPositions(nodes, ["n1", "n2"], "top")).toEqual({
      n1: [0, 0],
      n2: [300, 0],
    });
  });

  it("水平 / 垂直居中按包围盒中心", () => {
    // 包围盒 x: 0~500 → 中心 250；y: 0~300 → 中心 150
    const h = alignPositions(nodes, ["n1", "n2"], "hcenter");
    expect(h.n1[0]).toBeCloseTo(250 - 50);
    expect(h.n2[0]).toBeCloseTo(250 - 100);
    const v = alignPositions(nodes, ["n1", "n2"], "vcenter");
    expect(v.n1[1]).toBeCloseTo(150 - 50);
    expect(v.n2[1]).toBeCloseTo(150 - 50);
  });

  it("少于两张不做对齐", () => {
    expect(alignPositions(nodes, ["n1"], "left")).toEqual({});
  });
});

describe("连线", () => {
  it("同一端口只保留最后一条", () => {
    let links = connect([], "a", "c", 0);
    links = connect(links, "b", "c", 0);
    expect(links).toEqual([{ src: "b", dst: "c", port: 0 }]);
    expect(connect(links, "b", "c", 1)).toHaveLength(2);
  });

  it("环路检测", () => {
    const links = [
      { src: "a", dst: "b", port: 0 },
      { src: "b", dst: "c", port: 0 },
    ];
    expect(wouldCycle(links, "c", "a")).toBe(true);
    expect(wouldCycle(links, "a", "c")).toBe(false);
    expect(wouldCycle([], "a", "a")).toBe(true);
  });
});

describe("工程 JSON 往返", () => {
  it("导出导入保持一致", () => {
    const nodes = [
      node("n1", "base", [40, 60], { size: [320, 180], font_size: 14 }),
      node("n2", "result", [400, 60]),
    ];
    const links = [{ src: "n1", dst: "n2", port: 0 }];
    const json = graphToJSON(nodes, links, 1.25, "工程A");
    const back = jsonToGraph(json, schema);

    expect(back.name).toBe("工程A");
    expect(back.zoom).toBe(1.25);
    expect(back.nodes[0]).toMatchObject({
      id: "n1",
      type: "base",
      size: [320, 180],
      font_size: 14,
      fields: { stat_base: "1000", multiplier: "200" },
    });
    expect(back.links).toEqual(links);
  });

  it("折叠状态随工程 JSON 往返；旧存档缺该字段时按展开处理", () => {
    const nodes = [
      node("n1", "dmg", [40, 60], { collapsed: true }),
      node("n2", "res", [400, 60]),
    ];
    const json = graphToJSON(nodes, [], 1, "折叠");
    // 始终写出布尔值，便于后端 / 旧版读取
    expect(json.nodes[0].collapsed).toBe(true);
    expect(json.nodes[1].collapsed).toBe(false);

    const back = jsonToGraph(json, schema);
    expect(back.nodes[0].collapsed).toBe(true);
    expect(back.nodes[1].collapsed).toBe(false);

    const legacy = jsonToGraph(
      { nodes: [{ id: "n1", type: "dmg", pos: [0, 0], fields: {} }], links: [] },
      schema,
    );
    expect(legacy.nodes[0].collapsed).toBe(false);
  });

  it("兼容旧存档：缺 size/font_size/inputs，旧配方写法", () => {
    const legacy = {
      version: 1,
      app: "GenshinDamageCalc",
      nodes: [
        { id: "n1", type: "amp", pos: [0, 0], fields: { formula: "蒸发·水→火", shield: false } },
        { id: "n2", type: "add", pos: [300, 0], fields: {} },
      ],
      links: [],
    };
    const back = jsonToGraph(legacy, schema);
    expect(back.nodes[0].fields.formula).toBe("蒸发·水→火");
    expect(back.nodes[0].size).toBeNull();
    expect(back.nodes[0].font_size).toBeNull();
    expect(back.nodes[1].inputs).toBe(2); // 加法卡保持默认 2
    expect(back.zoom).toBe(1);
  });

  it("丢掉未知类型与悬空连线", () => {
    const back = jsonToGraph(
      {
        nodes: [
          { id: "n1", type: "不存在的卡", pos: [0, 0], fields: {} },
          { id: "n2", type: "dmg", pos: [0, 0], fields: {} },
        ],
        links: [
          { src: "n1", dst: "n2", port: 0 },
          { src: "n2", dst: "n2", port: 0 },
          { src: "n2", dst: "n9", port: 0 },
        ],
      },
      schema,
    );
    expect(back.nodes.map((n) => n.id)).toEqual(["n2"]);
    expect(back.links).toEqual([]);
  });

  it("越界 zoom 被夹到 40%~250%", () => {
    expect(jsonToGraph({ zoom: 99, nodes: [] }, schema).zoom).toBe(2.5);
    expect(jsonToGraph({ zoom: 0.01, nodes: [] }, schema).zoom).toBe(0.25);
    expect(jsonToGraph({ zoom: "坏值", nodes: [] }, schema).zoom).toBe(1);
  });

  it("重建结果卡片时保留隐藏变量字段", () => {
    const json = {
      nodes: [
        {
          id: "r1",
          type: "result",
          pos: [0, 0],
          fields: { var_nc: "未暴击伤害", var_cr: "", var_ex: "期望伤害" },
        },
      ],
      links: [],
    };
    const back = jsonToGraph(json, schema);
    expect(back.nodes[0].fields.var_nc).toBe("未暴击伤害");
    expect(back.nodes[0].fields.var_ex).toBe("期望伤害");
    expect(back.nodes[0].fields.var_cr).toBe("");
  });
});

describe("角色容器（抽象角色命名空间）", () => {
  it("角色名要能用在 名字::变量 里：不能有空格 / : / 连续下划线，也不能数字开头", () => {
    for (const ok of ["雷神", "主C", "配置A", "角色1", "abc_1"]) {
      expect(validRoleName(ok)).toBe(true);
    }
    for (const bad of ["", "  ", " 雷神", "雷神 ", "有 空格", "a::b", "a:b", "a__b", "1abc", "a-b", "a.b"]) {
      expect(validRoleName(bad)).toBe(false);
    }
  });

  it("新建角色容器：尺寸够大、默认名不重名", () => {
    const first = makeNode(schema, "role", [0, 0], "n1");
    expect(first.size).toEqual([ROLE_W, ROLE_H]);
    expect(first.fields.role_name).toBe("角色1");

    // 连着新建：角色1 → 角色2 → 角色3（默认名不撞）
    const second = makeNode(schema, "role", [0, 0], "n2", {}, [first]);
    expect(second.fields.role_name).toBe("角色2");
    expect(nextRoleName([first, second])).toBe("角色3");
    expect(
      makeNode(schema, "role", [0, 0], "n3", {}, [first, second]).fields.role_name,
    ).toBe("角色3");
  });

  it("角色面板没测量前的估算尺寸也更大（否则落位会叠在一起）", () => {
    const role = node("n1", "role", [0, 0], { size: null, measured: undefined });
    expect(estimateSize(role)).toEqual({ w: ROLE_W, h: ROLE_H });
    const dmg = node("n2", "dmg", [0, 0], { size: null, measured: undefined });
    expect(estimateSize(dmg)).toEqual({ w: 300, h: 210 });
  });

  it("按卡片中心判定归属：中心落在面板里就算属于该角色", () => {
    const role = node("r1", "role", [100, 100], { size: [600, 400] });
    const inside = node("n1", "dmg", [200, 200]); // 中心 (350,305) 在 100..700 / 100..500 内
    const outside = node("n2", "dmg", [900, 200]);
    const boxes = roleBoxes([role, inside, outside]);

    expect(roleOfNode(inside, boxes)).toBe("角色1");
    expect(roleOfNode(outside, boxes)).toBe("");
    // 容器自身不属于任何角色
    expect(roleOfNode(role, boxes)).toBe("");
  });

  it("只看中心：卡片压在边界上但中心在内就算属于", () => {
    const role = node("r1", "role", [0, 0], { size: [600, 400] });
    // 卡片 300×210，放在 (450,300)：中心 (600,405) 刚好超出右下角 → 不算
    expect(roleOfNode(node("n1", "dmg", [450, 300]), roleBoxes([role]))).toBe("");
    // 放在 (430,280)：中心 (580,385) 仍在面板内 → 算
    expect(roleOfNode(node("n2", "dmg", [430, 280]), roleBoxes([role]))).toBe("角色1");
  });

  it("名字为空 / 非法的容器不参与归属（等于没画）", () => {
    const unnamed = node("r1", "role", [0, 0], { size: [600, 400], fields: { role_name: "" } });
    const bad = node("r2", "role", [0, 0], { size: [600, 400], fields: { role_name: "有 空格" } });
    const inside = node("n1", "dmg", [200, 200]);

    expect(roleBoxes([unnamed, bad, inside])).toHaveLength(0);
    expect(roleOfNode(inside, roleBoxes([unnamed, bad, inside]))).toBe("");
  });

  it("容器嵌套时取最小的那个（可预期、与绘制顺序无关）", () => {
    const outer = node("r1", "role", [0, 0], { size: [1000, 800], fields: { role_name: "外层" } });
    const inner = node("r2", "role", [100, 100], { size: [400, 300], fields: { role_name: "内层" } });
    const card = node("n1", "dmg", [150, 150]);

    expect(buildRoleMap([outer, inner, card])).toEqual({ r1: "", r2: "", n1: "内层" });
  });

  it("buildRoleMap 给每个节点一个角色名（没有就是空串）", () => {
    const role = node("r1", "role", [0, 0], { size: [600, 400] });
    const inside = node("n1", "dmg", [200, 200]);
    const outside = node("n2", "dmg", [900, 900]);

    expect(buildRoleMap([role, inside, outside])).toEqual({
      r1: "",
      n1: "角色1",
      n2: "",
    });
  });

  it("归属不进工程 JSON（位置能重算，不进求值载荷以外的持久化）", () => {
    const role = node("r1", "role", [0, 0], { size: [600, 400] });
    const inside = node("n1", "dmg", [200, 200], { role: "角色1" });
    const json = graphToJSON([role, inside], [], 1, "测试");

    expect(json.nodes.every((n) => !("role" in n))).toBe(true);
  });

  it("框选要忽略角色容器（它是一大块面板，否则框选必把它卷进来）", () => {
    // React Flow 的 getNodesInside 不看 selectable，所以这条规则只能由我们自己守
    expect(ignoredByBoxSelect(node("r1", "role", [0, 0]))).toBe(true);
    expect(ignoredByBoxSelect(node("n1", "dmg", [0, 0]))).toBe(false);
    expect(ignoredByBoxSelect(node("n2", "text", [0, 0]))).toBe(false);
  });

  it("拐力箭头（角色→角色）不会被端口范围检查丢掉", () => {    // 角色卡没有伤害端口（inputs=0），但拐力箭头走 port 0：
    // 若按 inputs 检查就会被 jsonToGraph 丢掉，存档一保存拐力就没了
    const json = {
      version: 1,
      app: "GenshinDamageCalc",
      zoom: 1,
      name: "",
      nodes: [
        { id: "r1", type: "role", pos: [0, 0], size: null, font_size: null, inputs: 0, fields: {} },
        { id: "r2", type: "role", pos: [700, 0], size: null, font_size: null, inputs: 0, fields: {} },
        { id: "n1", type: "dmg", pos: [0, 500], size: null, font_size: null, inputs: 1, fields: {} },
      ],
      links: [
        { src: "r1", dst: "r2", port: 0 },      // 拐力箭头
        { src: "n1", dst: "n1", port: 0 },       // 自连：丢掉
        { src: "n1", dst: "r1", port: 3 },       // 越界端口：丢掉
      ],
    } as unknown as GraphJSON;
    const back = jsonToGraph(json, schema);
    expect(back.links).toEqual([{ src: "r1", dst: "r2", port: 0 }]);
  });

  it("角色面板文本解析：认三种分隔符、跳过注释、只收词表里的宏", () => {
    const keys = ["atk", "atk_pct", "res_shred"];
    const text = ["# 注释", "atk = 2000", "atk_pct：40", "res_shred: 40", "怪东西 = 5", "", "坏行"].join(
      "\n",
    );
    expect(parsePanel(text, keys)).toEqual({ atk: "2000", atk_pct: "40", res_shred: "40" });
  });

  it("角色面板文本回写：按词表顺序、空值不写（往返稳定）", () => {
    const keys = ["atk", "atk_pct", "res_shred"];
    const text = formatPanel({ res_shred: "40", atk: "2000", atk_pct: "" }, keys);
    expect(text).toBe("atk = 2000\nres_shred = 40");
    expect(parsePanel(text, keys)).toEqual({ atk: "2000", res_shred: "40" });
  });

  it("角色面板自定义对外项：解析 out::名字（固定宏按词表顺序、自定义按出现顺序）", () => {
    const keys = ["atk", "atk_pct"];
    const text = ["atk = 2000", "out::gift = 40", "out::Bad = 1", "乱写的 = 9"].join("\n");
    const parsed = parseRolePanel(text, keys);
    expect(parsed.values).toEqual({ atk: "2000", "out::gift": "40" });
    expect(parsed.custom).toEqual(["gift"]);          // 非法名与陌生名字都不收
    // 回写：固定宏在前、自定义项在后，且往返稳定
    const back = formatRolePanel(parsed.values, keys, parsed.custom);
    expect(back).toBe("atk = 2000\nout::gift = 40");
    expect(parseRolePanel(back, keys)).toEqual(parsed);
    // 空值不写
    expect(formatRolePanel({ atk: "1", "out::gift": "" }, keys, ["gift"])).toBe("atk = 1");
    // 顺序：换一个自定义顺序，回写跟着变
    expect(
      formatRolePanel({ atk: "1", "out::a": "2", "out::b": "3" }, keys, ["b", "a"]),
    ).toBe("atk = 1\nout::b = 3\nout::a = 2");
  });

  it("自定义对外项名字规则来自 schema（不在前端另立一套）", () => {
    // 兜底正则 + __ 段
    expect(validCustomOut("gift_2")).toBe(true);
    expect(validCustomOut("Bad")).toBe(false);
    expect(validCustomOut("a__b")).toBe(false);
    expect(validCustomOut("")).toBe(false);
    // schema 给什么就用什么
    expect(validCustomOut("拐力A", "^[\\w\\u4e00-\\u9fa5]+$")).toBe(true);
    // schema 给的正则坏掉时不至于炸掉界面 → 退回兜底规则
    expect(validCustomOut("gift", "([")).toBe(true);
    // 新增一行时的建议名字：避开已占用的
    expect(nextCustomOutName([])).toBe("buff");
    expect(nextCustomOutName(["buff"])).toBe("buff2");
    expect(nextCustomOutName(["buff", "buff2"])).toBe("buff3");
  });

  it("画布面板的显示名单：解析空格/逗号/顿号分隔，回写用空格", () => {
    expect(parsePanelShow("atk crit_rate")).toEqual(["atk", "crit_rate"]);
    expect(parsePanelShow("atk, crit_rate、em")).toEqual(["atk", "crit_rate", "em"]);
    expect(parsePanelShow("  ")).toEqual([]);
    expect(formatPanelShow(["atk", "em"])).toBe("atk em");
    // 往返稳定
    expect(parsePanelShow(formatPanelShow(["atk_pct", "res_shred"])))
      .toEqual(["atk_pct", "res_shred"]);
  });

  it("面板变量卡的预设代码：每项 own:: + in::（宏名来自 schema，不硬编码）", () => {
    const text = panelPreset([{ key: "atk" }, { key: "em" }]);
    expect(text).toBe("atk = own::atk + in::atk\nem = own::em + in::em");
    // 14 个面板宏按 schema 顺序各来一行
    expect(panelPreset(schema.panelMacros).split("\n")).toHaveLength(
      schema.panelMacros.length,
    );
  });

  it("只有「拖进角色区域且内容为空」的变量卡才需要填预设", () => {
    const varNode = { type: "var", fields: { defs: "" } };
    expect(needsPanelPreset(varNode, "火神", false)).toBe(true);
    expect(needsPanelPreset(varNode, "", false)).toBe(false);          // 不在角色里
    expect(needsPanelPreset(varNode, "火神", true)).toBe(false);       // 已经填过
    expect(needsPanelPreset({ type: "var", fields: { defs: "x = 1" } }, "火神", false)).toBe(false);
    expect(needsPanelPreset({ type: "role", fields: { defs: "" } }, "火神", false)).toBe(false);
  });

  it("变量卡拖进角色区域且内容为空 → 自动填面板预设代码（区域外不填、填过不重复填）", () => {
    const graph = jsonToGraph(
      {
        version: 1,
        app: "GenshinDamageCalc",
        zoom: 1,
        name: "",
        nodes: [
          { id: "r1", type: "role", pos: [0, 0], size: null, font_size: null, inputs: 0,
            fields: { role_name: "火神" } },
          { id: "v1", type: "var", pos: [100, 100], size: null, font_size: null, inputs: 0,
            fields: { defs: "" } },
          { id: "v2", type: "var", pos: [3000, 3000], size: null, font_size: null, inputs: 0,
            fields: { defs: "" } },
        ],
        links: [],
      } as unknown as GraphJSON,
      schema,
    );

    const res = fillPresetForDropped(graph.nodes, ["v1", "v2"], schema.panelMacros, []);
    const defs = (id: string) =>
      String(res.nodes.find((n) => n.id === id)?.fields.defs ?? "");
    expect(defs("v1")).toContain("atk = own::atk + in::atk");   // 区域内 → 填
    expect(defs("v2")).toBe("");                                 // 区域外 → 不填
    expect(res.filled).toEqual(["v1"]);

    // 已经填过的 id 不再回填（用户把卡片清空后不该被反复填）
    const again = fillPresetForDropped(res.nodes, ["v1"], schema.panelMacros, ["v1"]);
    expect(again.filled).toEqual([]);
    expect(String(again.nodes.find((n) => n.id === "v1")?.fields.defs)).toBe(
      defs("v1"),
    );
  });

  it("武器也是命名空间容器但没有面板；武器区域里的卡片归它", () => {
    const g = jsonToGraph(
      {
        version: 1,
        app: "GenshinDamageCalc",
        zoom: 1,
        name: "",
        nodes: [
          { id: "w1", type: "weapon", pos: [0, 0], size: null, font_size: null, inputs: 0,
            fields: { role_name: "武器A" } },
          { id: "r1", type: "role", pos: [900, 0], size: null, font_size: null, inputs: 0,
            fields: { role_name: "火神" } },
          { id: "n1", type: "dmg", pos: [120, 120], size: null, font_size: null, inputs: 1,
            fields: {} },
        ],
        links: [],
      } as unknown as GraphJSON,
      schema,
    );
    const find = (id: string) => g.nodes.find((n) => n.id === id)!;
    expect(isNamespaceNode(find("w1"))).toBe(true);
    expect(isPanelNode(find("w1"))).toBe(false);   // 武器没有面板
    expect(isNamespaceNode(find("r1"))).toBe(true);
    expect(isPanelNode(find("r1"))).toBe(true);
    expect(isNamespaceNode(find("n1"))).toBe(false);
    expect(buildRoleMap(g.nodes)["n1"]).toBe("武器A");   // 卡片归武器命名空间
  });

  it("normalizeSchema 给旧后端缺的字段补默认值（否则界面会白屏）", () => {
    // 旧后端可能没有 panelMacros / hidden_fields 这些新字段，
    // 前端直接 .map 就会抛异常 → 这里统一补成空数组
    const old = {
      version: 1,
      app: "GenshinDamageCalc",
      groups: undefined,
      nodeTypes: { dmg: { type: "dmg", title: "增伤区" } },
      presets: undefined,
      tables: undefined,
      resultVarFields: undefined,
      panelMacros: undefined,
      zoom: { min: 0.25, max: 2.5 },
      history: { max: 80 },
    } as unknown as Schema;
    const s = normalizeSchema(old);

    expect(s?.panelMacros).toEqual([]);
    expect(s?.groups).toEqual([]);
    expect(s?.resultVarFields).toEqual([]);
    expect(s?.nodeTypes.dmg.hidden_fields).toEqual([]);
    expect(s?.nodeTypes.dmg.fields).toEqual([]);
    expect(s?.nodeTypes.dmg.defaults).toEqual({});
    // 完全拿不到 schema 时返回 null（由调用方决定怎么提示）
    expect(normalizeSchema(null)).toBeNull();
  });
});
