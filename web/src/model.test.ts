/** 画布模型纯函数测试（落位 / 对齐 / 预设 / 工程 JSON 往返）。 */
import { describe, expect, it } from "vitest";
import {
  addPreset,
  alignPositions,
  areaFree,
  chainOrigin,
  connect,
  estimateSize,
  freeSlot,
  graphToJSON,
  jsonToGraph,
  makeNode,
  nextNodeId,
  spreadChain,
  wouldCycle,
} from "./model";
import type { CardNode, Schema } from "./types";
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
