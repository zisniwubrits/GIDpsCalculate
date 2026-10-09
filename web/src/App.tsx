/**
 * 原神伤害计算器 · Web 前端主界面。
 *
 * 职责边界：**前端不做任何伤害计算**，只负责画布交互与渲染；
 * 每次改动都把整张图 POST 给 Python 后端，拿回每个卡片的输出文案显示。
 */
import {
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  ReactFlowProvider,
  SelectionMode,
  useReactFlow,
  useViewport,
  type Connection,
  type EdgeChange,
  type NodeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { buildReport } from "./api";
import { copyText } from "./clipboard";
import CardNode, { type CardData, type CardRFNode, type MenuKind } from "./components/CardNode";
import CardEdge, { type CardRFEdge } from "./components/CardEdge";
import ContextMenu, { type MenuItem } from "./components/ContextMenu";
import { HelpDialog, ResultVarsDialog } from "./components/Dialogs";
import Sidebar from "./components/Sidebar";
import Toolbar from "./components/Toolbar";
import { downloadText, pickTextFile } from "./download";
import {
  CARD_DRAG_HANDLE,
  addPreset,
  alignPositions,
  connect,
  estimateSize,
  freeSlot,
  graphToJSON,
  jsonToGraph,
  makeNode,
  nextNodeId,
  wouldCycle,
  type AlignMode,
  type SizeOf,
} from "./model";
import { loadLocal, saveLocal } from "./state/persistence";
import { useEvaluate, useHelp, useSchema } from "./state/useBackend";
import { useGraphHistory, type GraphState } from "./state/useGraphHistory";
import type { CardNode as CardNodeModel, FieldValue, GraphJSON, NodeResult, Schema } from "./types";

const NODE_TYPES = { card: CardNode };
const EDGE_TYPES = { card: CardEdge };

/** 连线的稳定 id：源→目标#端口。 */
export const edgeId = (src: string, dst: string, port: number) => `${src}->${dst}#${port}`;

function parsePort(handle?: string | null): number {
  const m = /^in-(\d+)$/.exec(handle ?? "");
  return m ? Number(m[1]) : 0;
}

function BackendDown({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div className="boot boot-error" data-testid="backend-down">
      <div className="boot-box">
        <h1>连不上后端</h1>
        <p className="boot-msg">{error}</p>
        <p>请在仓库根目录启动后端，然后点「重试」：</p>
        <pre>python main.py</pre>
        <p className="boot-dim">
          开发前端时另开一个终端：<code>cd web &amp;&amp; pnpm dev</code>（已把 /api 代理到后端）
        </p>
        <button type="button" className="primary" onClick={onRetry}>
          重试
        </button>
      </div>
    </div>
  );
}

export default function App() {
  const { schema, error, reload } = useSchema();
  const help = useHelp();

  if (error) return <BackendDown error={error} onRetry={reload} />;
  if (!schema) return <div className="boot">正在连接后端…</div>;
  return (
    <ReactFlowProvider>
      <Board schema={schema} help={help} />
    </ReactFlowProvider>
  );
}

function Board({ schema, help }: { schema: Schema; help: { text: string; sections: string[] } }) {
  const initial = useMemo(() => {
    const stored = loadLocal();
    const parsed = stored ? jsonToGraph(stored, schema) : null;
    return {
      state: { nodes: parsed?.nodes ?? [], links: parsed?.links ?? [] } as GraphState,
      name: parsed?.name ?? "",
      zoom: parsed?.zoom ?? 1,
    };
  }, [schema]);

  const history = useGraphHistory(initial.state);
  const { nodes, links } = history.state;
  const [name, setName] = useState(initial.name);
  const [savedZoom, setSavedZoom] = useState(initial.zoom);
  const [dirty, setDirty] = useState(false);
  const [menu, setMenu] = useState<{ id: string; kind: MenuKind; x: number; y: number } | null>(
    null,
  );
  const [resultDialog, setResultDialog] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [toast, setToast] = useState("");
  const rf = useReactFlow<CardRFNode, CardRFEdge>();
  const { zoom: liveZoom } = useViewport();
  const lastSignature = useRef<string | null>(null);

  // -- 求值载荷：不含位置 / 尺寸（拖动卡片不该触发重新计算）-----------------
  const evalPayload = useMemo<GraphJSON>(
    () => ({
      version: 1,
      app: "GenshinDamageCalc",
      zoom: 1,
      name: "",
      nodes: nodes.map((n) => ({
        id: n.id,
        type: n.type,
        pos: [0, 0] as [number, number],
        size: null,
        font_size: null,
        inputs: n.inputs,
        fields: n.fields,
      })),
      links: links.map((l) => ({ ...l })),
    }),
    [nodes, links],
  );
  const evaluation = useEvaluate(evalPayload);
  const results = useMemo(() => evaluation.data?.nodes ?? {}, [evaluation.data]);

  // -- 序列化（脏标记 / 本地自动保存 / 导出）-------------------------------
  const graphJSON = useMemo(
    () => graphToJSON(nodes, links, savedZoom, name),
    [nodes, links, savedZoom, name],
  );
  const serialized = useMemo(() => JSON.stringify(graphJSON), [graphJSON]);

  useEffect(() => {
    if (lastSignature.current === null) {
      lastSignature.current = serialized; // 首次装载（含 StrictMode 重挂载）不算改动
      return;
    }
    if (lastSignature.current !== serialized) {
      lastSignature.current = serialized;
      setDirty(true);
    }
  }, [serialized]);

  useEffect(() => {
    const timer = setTimeout(() => saveLocal(JSON.parse(serialized) as GraphJSON), 400);
    return () => clearTimeout(timer);
  }, [serialized]);

  useEffect(() => {
    if (!dirty) return undefined;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  // -- 画布操作 -----------------------------------------------------------
  const apply = history.apply;
  const sizeOf: SizeOf = estimateSize;

  const onField = useCallback(
    (id: string, key: string, value: FieldValue) => {
      apply((s) => ({
        ...s,
        nodes: s.nodes.map((n) =>
          n.id === id ? { ...n, fields: { ...n.fields, [key]: value } } : n,
        ),
      }));
    },
    [apply],
  );

  const removeNode = useCallback(
    (id: string) => {
      apply((s) => ({
        nodes: s.nodes.filter((n) => n.id !== id),
        links: s.links.filter((l) => l.src !== id && l.dst !== id),
      }));
    },
    [apply],
  );

  const removeLink = useCallback(
    (id: string) => {
      apply((s) => ({ ...s, links: s.links.filter((l) => edgeId(l.src, l.dst, l.port) !== id) }));
      setSelectedEdge(null);
    },
    [apply],
  );

  const addNode = useCallback(
    (type: string) => {
      apply((s) => ({
        ...s,
        nodes: [...s.nodes, makeNode(schema, type, freeSlot(s.nodes, sizeOf), nextNodeId(s.nodes))],
      }));
    },
    [apply, schema, sizeOf],
  );

  const onPreset = useCallback(
    (preset: string) => {
      apply((s) => {
        const res = addPreset(schema, preset, s.nodes, s.links, sizeOf);
        return { nodes: res.nodes, links: res.links };
      });
    },
    [apply, schema, sizeOf],
  );

  const clearBoard = useCallback(() => {
    history.reset({ nodes: [], links: [] });
    setSelectedEdge(null);
  }, [history]);

  const onAlign = useCallback(
    (mode: AlignMode) => {
      apply((s) => {
        const ids = s.nodes.filter((n) => n.selected).map((n) => n.id);
        const moved = alignPositions(s.nodes, ids, mode, sizeOf);
        return { ...s, nodes: s.nodes.map((n) => (moved[n.id] ? { ...n, pos: moved[n.id] } : n)) };
      });
    },
    [apply, sizeOf],
  );

  const clearSelection = useCallback(() => {
    apply((s) => ({
      ...s,
      nodes: s.nodes.map((n) => (n.selected ? { ...n, selected: false } : n)),
    }));
    setSelectedEdge(null);
  }, [apply]);

  const selectAll = useCallback(() => {
    apply((s) => ({
      ...s,
      nodes: s.nodes.map((n) => (n.selected ? n : { ...n, selected: true })),
    }));
  }, [apply]);

  // -- React Flow 交互 ----------------------------------------------------
  const onNodesChange = useCallback(
    (changes: NodeChange<CardRFNode>[]) => {
      apply((s) => {
        let next = s.nodes;
        let nextLinks = s.links;
        for (const ch of changes) {
          if (ch.type === "position" && ch.position) {
            const pos = ch.position;
            next = next.map((n) => (n.id === ch.id ? { ...n, pos: [pos.x, pos.y] } : n));
          } else if (ch.type === "select") {
            next = next.map((n) => (n.id === ch.id ? { ...n, selected: ch.selected } : n));
          } else if (ch.type === "dimensions" && ch.dimensions) {
            const dim = ch.dimensions;
            // resizing / setAttributes 都是「用户在缩放」的信号；挂载时的首次测量
            // 两者都没有，此时只记 measured，不能当成用户设定尺寸。
            const byResize = Boolean(ch.resizing) || Boolean(ch.setAttributes);
            next = next.map((n) =>
              n.id === ch.id
                ? {
                    ...n,
                    measured: { width: dim.width, height: dim.height },
                    resizing: byResize,
                    size: byResize ? [dim.width, dim.height] : n.size,
                  }
                : n,
            );
          } else if (ch.type === "remove") {
            next = next.filter((n) => n.id !== ch.id);
            nextLinks = nextLinks.filter((l) => l.src !== ch.id && l.dst !== ch.id);
          }
        }
        return { nodes: next, links: nextLinks };
      });
    },
    [apply],
  );

  const onEdgesChange = useCallback(
    (changes: EdgeChange<CardRFEdge>[]) => {
      for (const ch of changes) {
        if (ch.type === "remove") removeLink(ch.id);
        else if (ch.type === "select") setSelectedEdge(ch.selected ? ch.id : null);
      }
    },
    [removeLink],
  );

  const onConnect = useCallback(
    (conn: Connection) => {
      const source = conn.source;
      const target = conn.target;
      if (!source || !target) return;
      const port = parsePort(conn.targetHandle);
      apply((s) => {
        const targetNode = s.nodes.find((n) => n.id === target);
        if (!targetNode || port >= targetNode.inputs) return s;
        if (wouldCycle(s.links, source, target)) return s;
        return { ...s, links: connect(s.links, source, target, port) };
      });
      setSelectedEdge(null);
    },
    [apply],
  );

  const isValidConnection = useCallback(
    (conn: Connection | CardRFEdge) => {
      const { source, target } = conn;
      if (!source || !target || source === target) return false;
      if (wouldCycle(links, source, target)) return false;
      const targetNode = nodes.find((n) => n.id === target);
      return Boolean(targetNode && parsePort(conn.targetHandle) < targetNode.inputs);
    },
    [links, nodes],
  );

  // -- 文件操作 -----------------------------------------------------------
  const doSave = useCallback(() => {
    const base = name.trim() || "伤害工程";
    downloadText(`${base}.json`, JSON.stringify(graphJSON, null, 2), "application/json");
    setDirty(false);
    setToast(`已导出 ${base}.json`);
  }, [graphJSON, name]);

  const doOpen = useCallback(async () => {
    const text = await pickTextFile();
    if (text === null) return;
    try {
      const parsed = jsonToGraph(JSON.parse(text) as unknown, schema);
      history.reset({ nodes: parsed.nodes, links: parsed.links });
      setName(parsed.name);
      setSavedZoom(parsed.zoom);
      rf.setViewport({ x: 0, y: 0, zoom: parsed.zoom });
      setDirty(false);
      setToast(`已打开工程（${parsed.nodes.length} 张卡片）`);
    } catch (e) {
      setToast(`打开失败：${(e as Error).message}`);
    }
  }, [history, rf, schema]);

  const doExport = useCallback(async () => {
    try {
      const res = await buildReport(graphJSON, { title: name.trim() || undefined });
      downloadText(res.filename, res.text);
      setToast(`已导出 ${res.filename}`);
    } catch (e) {
      setToast(`导出失败：${(e as Error).message}`);
    }
  }, [graphJSON, name]);

  // -- 复制 / 右键菜单 ----------------------------------------------------
  const copyNodeValue = useCallback(
    (id: string, triple = false) => {
      const r: NodeResult | undefined = results[id];
      if (!r) return;
      const text = triple && r.plainTriple.length === 3 ? r.plainTriple.join(" / ") : r.plain;
      void copyText(text).then((ok) => setToast(ok ? `已复制：${text}` : "复制失败"));
    },
    [results],
  );

  const onCopy = useCallback((id: string) => copyNodeValue(id), [copyNodeValue]);

  const setFontSize = useCallback(
    (id: string, value: number | null) => {
      apply((s) => ({
        ...s,
        nodes: s.nodes.map((n) =>
          n.id === id ? { ...n, font_size: value && value > 0 ? value : null } : n,
        ),
      }));
    },
    [apply],
  );

  /** 缩放结束：把最终尺寸与左上角坐标写回模型（拖动缩放是界面行为，不进求值载荷）。 */
  const onResize = useCallback(
    (id: string, size: [number, number], pos: [number, number]) => {
      apply((s) => ({
        ...s,
        nodes: s.nodes.map((n) =>
          n.id === id ? { ...n, size, pos, resizing: false } : n,
        ),
      }));
    },
    [apply],
  );

  const setResultVars = useCallback(
    (id: string, values: Record<string, string>) => {
      apply((s) => ({
        ...s,
        nodes: s.nodes.map((n) => (n.id === id ? { ...n, fields: { ...n.fields, ...values } } : n)),
      }));
    },
    [apply],
  );

  const menuItems = useMemo<MenuItem[]>(() => {
    if (!menu) return [];
    const node = nodes.find((n) => n.id === menu.id);
    if (!node) return [];
    const spec = schema.nodeTypes[node.type];
    const items: MenuItem[] = [];
    if (spec.ctx_menu) {
      items.push({ label: "设置结果变量…", onClick: () => setResultDialog(menu.id) });
      items.push({
        label: "清除结果变量",
        onClick: () => setResultVars(menu.id, { var_nc: "", var_cr: "", var_ex: "" }),
      });
    }
    if (spec.font_menu) {
      items.push({
        label: "加大字号",
        onClick: () => setFontSize(menu.id, (node.font_size ?? 13) + 2),
      });
      items.push({
        label: "减小字号",
        onClick: () => setFontSize(menu.id, Math.max(9, (node.font_size ?? 13) - 2)),
      });
      items.push({ label: "重置字号", onClick: () => setFontSize(menu.id, null) });
      items.push({
        label: "复制文本",
        onClick: () => {
          void copyText(String(node.fields.content ?? ""));
        },
      });
    }
    if (spec.copyable || node.type === "result") {
      items.push({ label: "复制输出数值", onClick: () => copyNodeValue(menu.id) });
    }
    if (spec.copyable) {
      items.push({ label: "复制三元组", onClick: () => copyNodeValue(menu.id, true) });
    }
    if (spec.table === "vars") {
      const rows = results[menu.id]?.rows ?? [];
      items.push({
        label: "复制变量表",
        onClick: () => {
          void copyText(rows.map((r) => r.join("\t")).join("\n"));
        },
      });
    }
    if (spec.table === "relic") {
      const table = schema.tables.relic;
      items.push({
        label: "复制整表",
        onClick: () => {
          void copyText(
            [table.header, ...(table.rows ?? [])].map((r) => r.join("\t")).join("\n"),
          );
        },
      });
    }
    items.push({ label: "删除卡片", danger: true, onClick: () => removeNode(menu.id) });
    return items;
  }, [menu, nodes, schema, results, copyNodeValue, removeNode, setFontSize, setResultVars]);

  // -- 键盘快捷键 --------------------------------------------------------
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const typing =
        !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
      if (e.key === "F1") {
        e.preventDefault();
        setShowHelp((v) => !v);
        return;
      }
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) history.redo();
        else history.undo();
        return;
      }
      if (mod && e.key.toLowerCase() === "y") {
        e.preventDefault();
        history.redo();
        return;
      }
      if (mod && e.key.toLowerCase() === "s") {
        e.preventDefault();
        doSave();
        return;
      }
      if (mod && e.key.toLowerCase() === "a" && !typing) {
        e.preventDefault();
        selectAll();
        return;
      }
      if (e.key === "Escape" && !typing && !showHelp) clearSelection();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [history, clearSelection, selectAll, showHelp, doSave]);

  // -- 渲染 ---------------------------------------------------------------
  const rfNodes = useMemo<CardRFNode[]>(
    () =>
      nodes.map((n) => {
        const data: CardData = {
          node: n,
          spec: schema.nodeTypes[n.type],
          result: results[n.id] ?? null,
          fontSize: n.font_size ?? 0,
          table: tableFor(n, schema, results),
          onField,
          onDelete: removeNode,
          onResize,
          onMenu: (id, kind, ev) => setMenu({ id, kind, x: ev.clientX, y: ev.clientY }),
          onCopy,
        };
        const style = n.resizing
          ? undefined
          : n.size
            ? { width: n.size[0], height: n.size[1] }
            : undefined;
        return {
          id: n.id,
          type: "card" as const,
          position: { x: n.pos[0], y: n.pos[1] },
          data,
          style,
          selected: Boolean(n.selected),
          measured: n.measured,
          // 只有标题栏能拖动（见 model.ts 的说明）
          dragHandle: CARD_DRAG_HANDLE,
        };
      }),
    [nodes, schema, results, onField, removeNode, onCopy, onResize],
  );

  const rfEdges = useMemo<CardRFEdge[]>(
    () =>
      links.map((l) => {
        const id = edgeId(l.src, l.dst, l.port);
        return {
          id,
          type: "card" as const,
          source: l.src,
          target: l.dst,
          sourceHandle: "out",
          targetHandle: `in-${l.port}`,
          selected: selectedEdge === id,
          interactionWidth: 18,
          markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: "#2f6fa7" },
          data: {
            src: l.src,
            dst: l.dst,
            port: l.port,
            dim: Boolean(hoverId && l.src !== hoverId && l.dst !== hoverId),
            onDelete: removeLink,
          },
        };
      }),
    [links, selectedEdge, hoverId, removeLink],
  );

  const selectedCount = nodes.filter((n) => n.selected).length;
  const status = useMemo(() => {
    if (evaluation.error) return { kind: "error" as const, text: `后端错误：${evaluation.error}` };
    if (evaluation.pending) return { kind: "busy" as const, text: "计算中…" };
    const data = evaluation.data;
    if (!data) return { kind: "warn" as const, text: "等待计算…" };
    const warn = data.warnings[0];
    if (!data.ok) {
      return { kind: "warn" as const, text: warn ?? data.error ?? "未完成" };
    }
    const display = data.result?.display ?? "已计算";
    return { kind: warn ? ("warn" as const) : ("ok" as const), text: warn ? `${display} ｜ ${warn}` : display };
  }, [evaluation]);

  return (
    <div className="app">
      <Toolbar
        name={name}
        onName={setName}
        dirty={dirty}
        canUndo={history.canUndo}
        canRedo={history.canRedo}
        onUndo={history.undo}
        onRedo={history.redo}
        onSave={doSave}
        onOpen={() => void doOpen()}
        onExport={() => void doExport()}
        onClear={clearBoard}
        onHelp={() => setShowHelp(true)}
        zoom={liveZoom}
        onZoomIn={() => rf.zoomIn({ duration: 120 })}
        onZoomOut={() => rf.zoomOut({ duration: 120 })}
        onZoomReset={() => rf.zoomTo(1, { duration: 120 })}
        onFit={() => rf.fitView({ padding: 0.15, duration: 200 })}
        status={status}
      />

      <div className="main">
        <Sidebar
          schema={schema}
          selectedCount={selectedCount}
          onAdd={addNode}
          onPreset={onPreset}
          onAlign={onAlign}
          onClear={clearBoard}
          onClearSelection={clearSelection}
        />
        <div className="canvas" data-testid="canvas">
          <ReactFlow
            nodes={rfNodes}
            edges={rfEdges}
            nodeTypes={NODE_TYPES}
            edgeTypes={EDGE_TYPES}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            isValidConnection={isValidConnection}
            onNodeMouseEnter={(_, n) => setHoverId(n.id)}
            onNodeMouseLeave={() => setHoverId(null)}
            onMoveEnd={(_, vp) => setSavedZoom(vp.zoom)}
            onPaneClick={() => setMenu(null)}
            defaultViewport={{ x: 0, y: 0, zoom: initial.zoom }}
            minZoom={0.25}
            maxZoom={2.5}
            panOnScroll
            zoomOnScroll={false}
            zoomActivationKeyCode="Control"
            selectionOnDrag
            selectionMode={SelectionMode.Partial}
            panOnDrag={[1, 2]}
            selectionKeyCode={null}
            multiSelectionKeyCode="Shift"
            deleteKeyCode={["Delete"]}
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={18} size={1} color="#dfe6ee" />
            <Controls showInteractive={false} position="bottom-right" />
          </ReactFlow>
          {nodes.length === 0 ? (
            <div className="canvas-empty">
              <p>画布是空的</p>
              <p className="dim">
                从左边的「卡片」菜单添加乘区卡片，或点「一键预设」搭一条链，
                最后接一张 ★结果 汇总伤害。
              </p>
            </div>
          ) : null}
        </div>
      </div>

      {menu ? (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          items={menuItems}
          onClose={() => setMenu(null)}
          testId={`ctx-${menu.kind}`}
        />
      ) : null}

      {resultDialog ? (
        <ResultVarsDialog
          initial={Object.fromEntries(
            schema.resultVarFields.map((f) => [
              f.key,
              String(nodes.find((n) => n.id === resultDialog)?.fields[f.key] ?? ""),
            ]),
          )}
          labels={schema.resultVarFields}
          onSave={(values) => {
            setResultVars(resultDialog, values);
            setResultDialog(null);
          }}
          onClear={() => {
            setResultVars(resultDialog, { var_nc: "", var_cr: "", var_ex: "" });
            setResultDialog(null);
          }}
          onClose={() => setResultDialog(null)}
        />
      ) : null}

      {showHelp ? (
        <HelpDialog text={help.text} sections={help.sections} onClose={() => setShowHelp(false)} />
      ) : null}

      {toast ? (
        <button type="button" className="toast" onClick={() => setToast("")}>
          {toast}
        </button>
      ) : null}
    </div>
  );
}

/** 表格类卡片（理想圣遗物 / 变量表）的内容。 */
function tableFor(
  node: CardNodeModel,
  schema: Schema,
  results: Record<string, NodeResult>,
): { header: string[]; rows: string[][] } | null {
  const spec = schema.nodeTypes[node.type];
  if (!spec.table) return null;
  if (spec.table === "relic") {
    const t = schema.tables.relic;
    return { header: t.header, rows: t.rows ?? [] };
  }
  return {
    header: schema.tables.vars.header,
    rows: results[node.id]?.rows ?? [["（暂无变量）", ""]],
  };
}
