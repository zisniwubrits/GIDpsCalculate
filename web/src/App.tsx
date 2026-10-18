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
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { fetchStorage, health, openProject, saveProject, saveReport } from "./api";
import { copyText, readText } from "./clipboard";
import CardNode, {
  ROLE_BOX_COLLIDING_STYLE,
  type CardData,
  type CardRFNode,
  type MenuKind,
} from "./components/CardNode";
import CardEdge, { type CardRFEdge } from "./components/CardEdge";
import CanvasWatermark from "./components/CanvasWatermark";
import ContextMenu, { type MenuItem } from "./components/ContextMenu";
import {
  HelpDialog,
  NameCardDialog,
  NewProjectDialog,
  ResultVarsDialog,
  RoleNameDialog,
  RolePanelDialog,
} from "./components/Dialogs";
import Sidebar from "./components/Sidebar";
import Toolbar from "./components/Toolbar";
import {
  CARD_DRAG_HANDLE,
  addPreset,
  alignPositions,
  buildRoleMap,
  cardsBlockingHide,
  cardsHidden,
  cardsInside,
  clipboardFromText,
  clipboardToText,
  collectClipboard,
  connect,
  duplicateRoleNames,
  estimateSize,
  fillPresetForDropped,
  formatRolePanel,
  formatPanelShow,
  freeSlot,
  graphToJSON,
  hiddenCardsFor,
  ignoredByBoxSelect,
  jsonToGraph,
  makeNode,
  nextNodeId,
  parseRolePanel,
  pasteClipboard,
  roleBoxCollisions,
  roleNameError,
  resolveRoleOverlaps,
  isBuffPair,
  isNamespaceNode,
  isPanelNode,
  parsePanelShow,
  toggleRoleCardsHidden,
  wouldCycle,
  type AlignMode,
  type ClipboardPayload,
  type SizeOf,
  isMatrixNode,
} from "./model";
import MatrixPanelDialog from "./components/MatrixPanelDialog";
import { cellPanel, type CellPanel } from "./api";
import { loadLocal, saveLocal } from "./state/persistence";
import { useEvaluate, useHelp, useSchema } from "./state/useBackend";
import { useGraphHistory, type GraphState } from "./state/useGraphHistory";
import type {
  CardNode as CardNodeModel,
  FieldValue,
  GraphJSON,
  NodeResult,
  Schema,
} from "./types";

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
    // 旧工程里可能已经有两个角色区域压在一起（这条规则是后加的）：
    // 打开时按顺序把后来的挪开，并把结果 / 提示一并向界面汇报（见下面的 useMemo）。
    const fixed = parsed ? resolveRoleOverlaps(parsed.nodes) : null;
    return {
      state: { nodes: fixed?.nodes ?? [], links: parsed?.links ?? [] } as GraphState,
      name: parsed?.name ?? "",
      zoom: parsed?.zoom ?? 1,
      overlapsMoved: fixed?.moved ?? [],
    };
  }, [schema]);

  /**
   * React Flow 自己也会存一份节点位置：把节点挡回原处时**它内部那份还是拖动后的**，
   * 只改我们的状态它不会跟（画布上还停在压住别人的地方）。这个计数器强制重算
   * rfNodes（对象引用变了 → RF 重新对账并采纳我们的位置）。
   */
  const [revision, setRevision] = useState(0);
  /** 最新的节点数组（给"回滚位置"这类 apply 之后的副作用用，避免闭包拿到旧值） */
  const nodesRef = useRef<CardNodeModel[]>([]);

  const history = useGraphHistory(initial.state);
  const { nodes, links } = history.state;
  nodesRef.current = nodes;
  const [name, setName] = useState(initial.name);
  /** 一键保存的落地目录（后端记忆，打开/保存后同步） */
  const [saveDir, setSaveDir] = useState("");
  /** 前端产物过期的提示文案（后端 /api/health 判定，空串表示正常） */
  const [staleHint, setStaleHint] = useState("");
  /** 后端报的前端产物构建时间：显示在状态区，用来确认浏览器加载的是不是最新包 */
  const [buildTime, setBuildTime] = useState("");
  const [savedZoom, setSavedZoom] = useState(initial.zoom);
  const [dirty, setDirty] = useState(false);
  const [menu, setMenu] = useState<{ id: string; kind: MenuKind; x: number; y: number } | null>(
    null,
  );
  const [resultDialog, setResultDialog] = useState<string | null>(null);
  /** 正在「命名卡片…」的节点 id（null = 没打开） */
  const [nameDialog, setNameDialog] = useState<string | null>(null);
  /** 正在打开「角色面板…」的节点 id（null = 没打开） */
  const [panelDialog, setPanelDialog] = useState<string | null>(null);
  /** 正在「设置角色名…」的节点 id（null = 没打开） */
  const [roleNameDialog, setRoleNameDialog] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  /** 轻提示：显示 5 秒后自动消失（点一下也能立刻关掉） */
  const [toast, setToast] = useState("");
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 5000);
    return () => clearTimeout(timer);
  }, [toast]);
  const rf = useReactFlow<CardRFNode, CardRFEdge>();
  const { zoom: liveZoom } = useViewport();
  const lastSignature = useRef<string | null>(null);
  /** 正在拖框选：此时忽略「角色容器」的选中变化（见 model.ignoredByBoxSelect） */
  const boxSelecting = useRef(false);
  /** 框选时是否也选角色/武器域（工具栏「框选域」开关，默认关；见 ignoredByBoxSelect） */
  const [boxSelectDomains, setBoxSelectDomains] = useState(false);
  /** 是否显示域间箭头（角色/武器之间的拐力箭头；默认隐藏，纯显示开关，不影响求值） */
  // 「域间箭头」是**显示开关**：默认关（用户要求），但要记住上次的选择 ——
  // 否则保存 / 重载之后拐力箭头全被藏起来，看起来像"线丢了"（用户报的 bug）。
  const [showDomainArrows, setShowDomainArrows] = useState(() => {
    try {
      return window.localStorage.getItem("genshin-dmg-calc:show-domain-arrows") === "1";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      window.localStorage.setItem(
        "genshin-dmg-calc:show-domain-arrows",
        showDomainArrows ? "1" : "0",
      );
    } catch {
      /* 存不下也没关系，下次回到默认关 */
    }
  }, [showDomainArrows]);
  /** 鼠标在画布上的**屏幕坐标**（粘贴时换算成流坐标，把卡片放到鼠标附近） */
  const pointer = useRef<{ x: number; y: number } | null>(null);
  /** 拖动角色区域被"重叠"规则挡回时，记下要写回 React Flow 的位置（apply 之后处理） */
  const revertTo = useRef<{ id: string; pos: [number, number]; blockedBy: CardNodeModel[] } | null>(
    null,
  );
  /** 拖动开始前角色区域的位置（松手时若压上了就整个回滚到这里） */
  const dragStart = useRef<Map<string, [number, number]>>(new Map());
  /** 加载工程时自动挪开重叠角色区域的提示（只在第一次渲染后弹一次） */
  const overlapNotice = useRef(
    initial.overlapsMoved.length
      ? `打开时发现角色区域互相压着，已自动挪开 ${initial.overlapsMoved.length} 个（角色区域不许重叠）`
      : "",
  );
  useEffect(() => {
    if (overlapNotice.current) {
      setToast(overlapNotice.current);
      setDirty(true);            // 位置被改过 → 提示"未保存"，让用户决定是否落盘
      overlapNotice.current = "";
    }
  }, []);

  // -- 求值载荷：不含位置 / 尺寸（拖动卡片不该触发重新计算）-----------------
  // 角色归属（role）由位置推导：useEvaluate 按**序列化内容**去重，所以拖动时只有
  // 「卡片跨过容器边界、role 真的变了」才重算，不会刷求值。
  const roles = useMemo(() => buildRoleMap(nodes), [nodes]);
  const evalPayload = useMemo<GraphJSON>(
    () => ({
      version: 1,
      app: "GenshinDamageCalc",
      zoom: 1,
      name: "",
      // 当前工程的落地目录：后端解析「外部域」卡片的**相对路径**时用它
      // （填 dds.json / dds 就指同目录下的那个文件）
      dir: saveDir || undefined,
      nodes: nodes.map((n) => ({
        id: n.id,
        type: n.type,
        pos: [0, 0] as [number, number],
        size: null,
        font_size: null,
        inputs: n.inputs,
        fields: n.fields,
        role: roles[n.id] ?? "",
      })),
      links: links.map((l) => ({ ...l })),
    }),
    [nodes, links, roles, saveDir],
  );
  const evaluation = useEvaluate(evalPayload);
  const results = useMemo(() => evaluation.data?.nodes ?? {}, [evaluation.data]);

  // 后端报的告警（目前只有「外部域」文件互相引用）：在界面底部提示一次。
  // 同一条只提示一次，免得每敲一个字就弹；问题消掉后再出现会重新提示。
  const warnKey = (evaluation.data?.warnings ?? []).join("\n");
  const lastWarn = useRef("");
  useEffect(() => {
    if (!warnKey) {
      lastWarn.current = "";
      return;
    }
    if (warnKey !== lastWarn.current) {
      lastWarn.current = warnKey;
      setToast(warnKey.split("\n").join("；"));
    }
  }, [warnKey]);

  // -- 序列化（脏标记 / 本地自动保存 / 导出）-------------------------------
  const graphJSON = useMemo(
    () => graphToJSON(nodes, links, savedZoom, name, roles),
    [nodes, links, savedZoom, name, roles],
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

  // 启动时问一次后端：一键保存会存到哪个目录
  useEffect(() => {
    const ctrl = new AbortController();
    fetchStorage(ctrl.signal)
      .then((s) => setSaveDir(s.dir))
      .catch(() => undefined);
    return () => ctrl.abort();
  }, []);

  // 前端产物过期提示：后端会比对 web/dist 与 web/src 的时间
  // （注意：这条提示本身要新 bundle 才看得到，所以 launcher 与启动日志也会提醒）
  useEffect(() => {
    const ctrl = new AbortController();
    health(ctrl.signal)
      .then((h) => {
        setBuildTime(h.webBuildTime ?? "");
        if (!h.webStale) return;
        setStaleHint(
          h.webBuilt
            ? `前端产物过期（${h.webBuildTime ?? "未知"}）：浏览器用的是旧界面，请重建 → cd web && pnpm build`
            : "还没有前端构建产物：请执行 cd web && pnpm build",
        );
      })
      .catch(() => undefined);
    return () => ctrl.abort();
  }, []);

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
        nodes: [...s.nodes, makeNode(schema, type, freeSlot(s.nodes, sizeOf), nextNodeId(s.nodes), {}, s.nodes)],
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

  /** 打开「新建项目」弹窗 */
  const [newDialog, setNewDialog] = useState(false);
  /** 已经被程序自动填过预设代码的变量卡（用户在清空后不会再被反复填） */
  const presetFilled = useRef<Set<string>>(new Set());
  /** schema 的引用：拖拽回调里要用 panelMacros，但不想因为它频繁重建回调 */
  const schemaRef = useRef(schema);
  useEffect(() => {
    schemaRef.current = schema;
  }, [schema]);

  /**
   * 新建项目：**先问工程名，再完整重置** —— 画布、工程名、撤销历史、
   * 浏览器本地自动存档（由持久化 effect 自动写回空白状态）。
   * 磁盘上的文件不动；保存目录也不动（那是后端记忆的偏好）。
   */
  const doNewProject = useCallback(
    (projectName: string) => {
      history.reset({ nodes: [], links: [] });
      setName(projectName);
      setSelectedEdge(null);
      setMenu(null);
      setResultDialog(null);
      setNameDialog(null);
      setPanelDialog(null);
      setNewDialog(false);
      setSavedZoom(1);
      rf.setViewport({ x: 0, y: 0, zoom: 1 });
      // 让下一次序列化比较被当成"首次装载"，于是新工程是干净状态（不显示未保存）
      lastSignature.current = null;
      setDirty(false);
      setToast(projectName ? `已新建项目：${projectName}` : "已新建空白项目");
    },
    [history, rf],
  );

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
            // 角色区域不许互相压 —— 但**拖动中不拦**：让卡片老老实实跟着指针走，
            // 同时把"压到谁"标红（看得见原因）。只有真压上了才在松手时回滚。
            //
            // 为什么要改：原来拖动中一旦压到就把位移顶回上一次合法位置，手感是
            // "走到某处就顶不动了"，而角色区域框（560×380）比看得见的内容（26px 高）
            // 大十几倍，用户看着没有碰撞却被顶回去，只能理解成"程序乱报不合法"。
            const placed: [number, number] = [pos.x, pos.y];
            const moving = s.nodes.find((n) => n.id === ch.id);
            if (moving && isNamespaceNode(moving)) {
              const hit = roleBoxCollisions(s.nodes, ch.id, placed, moving.size);
              const colliding = hit.length > 0;
              if (ch.dragging) {
                if (!dragStart.current.has(ch.id)) dragStart.current.set(ch.id, moving.pos);
                // 压到别人 → 把这个区域框描红（红框就是碰撞箱，一眼看出压到谁）
                next = next.map((n) =>
                  n.id === ch.id ? { ...n, colliding, pos: placed } : n,
                );
                continue;
              }
              // 松手：压上了就整趟回滚（并说清压到谁、区域框多大）
              if (colliding) {
                const start = dragStart.current.get(ch.id) ?? moving.pos;
                revertTo.current = { id: ch.id, pos: start, blockedBy: hit };
                const at = [start[0], start[1]] as [number, number];
                return {
                  ...s,
                  nodes: s.nodes.map((n) =>
                    n.id === ch.id ? { ...n, pos: at, colliding: false } : n,
                  ),
                };
              }
              dragStart.current.delete(ch.id);
            }
            next = next.map((n) =>
              n.id === ch.id ? { ...n, pos: placed, colliding: false } : n,
            );
            if (!ch.dragging) {
              // 拖拽结束：空白的变量卡落进角色区域 → 程序填入面板预设代码
              const res = fillPresetForDropped(
                next,
                [ch.id],
                schemaRef.current.panelMacros,
                Array.from(presetFilled.current),
              );
              next = res.nodes;
              res.filled.forEach((fid) => presetFilled.current.add(fid));
            }
          } else if (ch.type === "select") {
            next = next.map((n) =>
              n.id === ch.id &&
              !(ch.selected && boxSelecting.current && ignoredByBoxSelect(n, boxSelectDomains))
                ? { ...n, selected: ch.selected }
                : n,
            );
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
            // 缩放中角色区域压到别人：先允许（不然缩不动），在 onResize 结束时统一处理
          } else if (ch.type === "remove") {
            next = next.filter((n) => n.id !== ch.id);
            nextLinks = nextLinks.filter((l) => l.src !== ch.id && l.dst !== ch.id);
          }
        }
        return { nodes: next, links: nextLinks };
      });
      // apply 之后的副作用：把被挡回去的角色位置同步回 React Flow（否则画布上还停在重叠处）
      const back = revertTo.current;
      if (back) {
        revertTo.current = null;
        const put = () => {
          rf.updateNode(back.id, { position: { x: back.pos[0], y: back.pos[1] } });
          const live = rf.getNodes();
          rf.setNodes(
            live.map((n) => {
              const mine = nodesRef.current.find((m) => m.id === n.id);
              return mine ? { ...n, position: { x: mine.pos[0], y: mine.pos[1] } } : n;
            }),
          );
        };
        // React Flow 对"正在拖的节点"会忽略位置更新（拖动状态还没清掉），
        // 所以推到下一帧再写回，否则画布上仍停在压住别人的位置（实测踩到）
        put();
        if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => put());
        setRevision((v) => v + 1);
        // 说清"压到谁、被压的区域有多大"——角色区域框比看得见的内容大得多，
        // 只报一句"不许互相压"会被当成误报（用户就是这么反馈的）
        const names = back.blockedBy
          .map((n) => String(n.fields.role_name ?? "").trim() || "未命名")
          .join("、");
        const box = back.blockedBy[0];
        const size = box ? estimateSize(box) : null;
        setToast(
          size
            ? `压到了「${names}」的区域（约 ${Math.round(size.w)}×${Math.round(size.h)}，虚线范围就是它），已放回原处`
            : `压到了「${names}」的区域，已放回原处`,
        );
      }
    },
    [apply, rf, boxSelectDomains],
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

  /** 两个节点之间是不是「拐力箭头」（角色卡 → 角色卡） */
  const isBuffPairCb = useCallback(
    (source: string, target: string) => isBuffPair(nodes, source, target),
    [nodes],
  );

  const onConnect = useCallback(
    (conn: Connection) => {
      const source = conn.source;
      const target = conn.target;
      if (!source || !target) return;
      const port = parsePort(conn.targetHandle);
      const buff = isBuffPairCb(source, target);
      const dstIsMatrix = isMatrixNode(
        nodes.find((n) => n.id === target) ?? ({ type: "" } as CardNodeModel),
      );
      apply((s) => {
        const targetNode = s.nodes.find((n) => n.id === target);
        if (!targetNode) return s;
        // 拐力箭头（角色→角色）：端口与环路都不按伤害链的规则来
        // （拐力只作用于直接目标、不传递，所以成环也没关系）
        if (buff) {
          // 拐力箭头：目标是角色 → 端口恒为 0（角色只有一个入点）；
          // 目标是「域对照表」→ 保留点到的那个接入点（左上角 / 某行 / 某列）
          const port = dstIsMatrix ? parsePort(conn.targetHandle) : 0;
          return { ...s, links: connect(s.links, source, target, port) };
        }
        if (port >= targetNode.inputs) return s;
        if (wouldCycle(s.links, source, target)) return s;
        return { ...s, links: connect(s.links, source, target, port) };
      });
      setSelectedEdge(null);
    },
    [apply, isBuffPairCb],
  );

  const isValidConnection = useCallback(
    (conn: Connection | CardRFEdge) => {
      const { source, target } = conn;
      if (!source || !target || source === target) return false;
      if (isBuffPairCb(source, target)) return true;      // 角色标签之间：随便连（含双向）
      if (wouldCycle(links, source, target)) return false;
      const targetNode = nodes.find((n) => n.id === target);
      return Boolean(targetNode && parsePort(conn.targetHandle) < targetNode.inputs);
    },
    [links, nodes, isBuffPairCb],
  );

  // -- 文件操作（走后端写文件：一键保存、记忆目录）-------------------------
  const doSave = useCallback(async () => {
    try {
      const res = await saveProject(graphJSON);
      setSaveDir(res.dir);
      setDirty(false);
      setToast(`已保存到 ${res.path}`);
    } catch (e) {
      setToast(`保存失败：${(e as Error).message}`);
    }
  }, [graphJSON]);

  const doOpen = useCallback(async () => {
    try {
      const res = await openProject();
      if (res.cancelled) return;                  // 用户取消：静默
      if (!res.ok || !res.graph) {
        setToast(`打开失败：${res.error ?? "未知错误"}`);
        return;
      }
      const parsed = jsonToGraph(res.graph, schema);
      // 旧工程可能有两个同名角色 / 两个压在一起的角色区域（这两条规则是后加的）：
      // 压在一起的就挪开（并提示），重名只提示、不擅自改名（名字会写进 `名字::变量`）。
      const fixed = resolveRoleOverlaps(parsed.nodes);
      const dup = duplicateRoleNames(parsed.nodes);
      history.reset({ nodes: fixed.nodes, links: parsed.links });
      // 工程名跟着**文件名**走（用户要求）：打开哪个文件就叫什么名字，
      // 免得"文件叫 A.json、里面的工程名是 B"时保存写到别的文件去
      setName(projectNameFromPath(res.path) || parsed.name);
      setSavedZoom(parsed.zoom);
      rf.setViewport({ x: 0, y: 0, zoom: parsed.zoom });
      if (res.dir) setSaveDir(res.dir);           // 从哪读就往哪存
      // 让下一次序列化比较被当成"首次装载"：否则刚打开的工程会立刻显示「● 未保存」
      // （序列化内容跟上一份不同 → 脏标记被误置）
      lastSignature.current = null;
      setDirty(fixed.moved.length > 0);
      const notes = [
        `已打开 ${res.path}（${fixed.nodes.length} 张卡片）`,
        fixed.moved.length ? `挪开了 ${fixed.moved.length} 个重叠的角色区域` : "",
        dup.length ? `注意：有重名角色 ${dup.join("、")}（区域会互相干扰，建议改名）` : "",
      ].filter(Boolean);
      setToast(notes.join(" ｜ "));
    } catch (e) {
      setToast(`打开失败：${(e as Error).message}`);
    }
  }, [history, rf, schema]);

  const doExport = useCallback(async () => {
    try {
      const res = await saveReport(graphJSON, { title: name.trim() || undefined });
      setSaveDir(res.dir);
      setToast(`已导出报告 ${res.path}`);
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

  // -- 卡片 / 域的复制粘贴（Ctrl+C / Ctrl+V）------------------------------
  /** 内存里那一份（剪贴板读不到时兜底；正常路径是系统剪贴板里的 JSON） */
  const cardClipboard = useRef<ClipboardPayload | null>(null);

  /** 把一包卡片写进**系统剪贴板**（JSON）+ 内存兜底：Ctrl+C 与右键「复制…域」共用 */
  const copyCards = useCallback((payload: ClipboardPayload) => {
    if (!payload.nodes.length) {
      setToast("先选中卡片或角色/武器域，再 Ctrl+C");
      return;
    }
    cardClipboard.current = payload;
    const roles = payload.nodes.filter(isNamespaceNode).length;
    const cards = payload.nodes.length - roles;
    const what =
      roles && cards
        ? `${roles} 个域 + ${cards} 张卡片`
        : roles
          ? `${roles} 个域`
          : `${cards} 张卡片`;
    // 序列化成 JSON 写进系统剪贴板（静默完成，不再提示"可到别的页面粘贴"）
    void copyText(clipboardToText(payload)).then((ok) => {
      if (!ok) setToast(`已复制 ${what}（剪贴板写入失败，仅本页可粘贴）`);
    });
  }, []);

  /** Ctrl+C：选中的卡片 → 卡片；选中的角色/武器域 → 域 + 域内卡片 + 域内连线 */
  const doCopyCards = useCallback(() => {
    copyCards(collectClipboard(nodes, links));
  }, [nodes, links, copyCards]);

  /** Ctrl+Shift+C：把选中卡片的输出数值复制成文本（原来的"复制数值"）。 */
  const doCopyValues = useCallback(() => {
    const picked = nodes.filter((n) => n.selected);
    if (!picked.length) {
      setToast("先选中卡片，再 Ctrl+Shift+C 复制数值");
      return;
    }
    const lines = picked
      .map((n) => results[n.id])
      .filter(Boolean)
      .map((r) => (r as NodeResult).plain);
    if (!lines.length) {
      setToast("选中的卡片还没有算好的数值");
      return;
    }
    const text = lines.join("\n");
    void copyText(text).then((ok) => setToast(ok ? `已复制数值：${text}` : "复制失败"));
  }, [nodes, results]);

  /** Ctrl+V：优先读**系统剪贴板**里的卡片 JSON（可跨页面/跨浏览器），读不到就用内存那份 */
  const doPasteCards = useCallback(async () => {
    const text = await readText();
    const fromClipboard = text ? clipboardFromText(text, schema) : null;
    const payload = fromClipboard ?? cardClipboard.current;
    if (!payload || !payload.nodes.length) {
      setToast("剪贴板里没有卡片（先在画布上选中卡片或域，按 Ctrl+C）");
      return;
    }
    // 粘贴位置：鼠标在哪儿就贴到哪儿（换算成流坐标；鼠标还没进过画布则退回找空白）
    const anchor = pointer.current
      ? rf.screenToFlowPosition({ x: pointer.current.x, y: pointer.current.y })
      : null;
    apply((s) => {
      const res = pasteClipboard(
        payload,
        s.nodes,
        s.nodes.map((n) => n.id),
        estimateSize,
        anchor ? [anchor.x, anchor.y] : null,
      );
      return { nodes: res.nodes, links: [...s.links, ...res.links] };
    });
    const roles = payload.nodes.filter(isNamespaceNode).length;
    const cards = payload.nodes.length - roles;
    const what =
      roles && cards
        ? `${roles} 个域 + ${cards} 张卡片`
        : roles
          ? `${roles} 个域`
          : `${cards} 张卡片`;
    setToast(`已粘贴 ${what}${fromClipboard ? "" : "（来自本页缓存）"}`);
  }, [apply, schema, rf]);

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
  /** 「域对照表」右键单元格：拿这一格的角色面板（汇总行列拐力之后） */
  const [cellPanelData, setCellPanelData] = useState<CellPanel | null>(null);
  const onCellPanel = useCallback(
    (id: string, row: number, col: number) => {
      void cellPanel({
        graph: {
          version: 1,
          app: "GenshinDamageCalc",
          zoom: 1,
          name,
          nodes: nodes.map((n) => ({
            id: n.id,
            type: n.type,
            pos: [n.pos[0], n.pos[1]] as [number, number],
            size: n.size ? ([n.size[0], n.size[1]] as [number, number]) : null,
            font_size: n.font_size,
            inputs: n.inputs,
            fields: { ...n.fields },
            collapsed: Boolean(n.collapsed),
            role: roles[n.id] ?? "",
          })),
          links: links.map((l) => ({ src: l.src, dst: l.dst, port: l.port })),
        },
        nodeId: id,
        row,
        col,
        dir: saveDir,
      })
        .then((res) => {
          if (!res.ok) {
            setToast(`面板读取失败：${res.error ?? "未知错误"}`);
            return;
          }
          setCellPanelData(res);
        })
        .catch((e) => setToast(`面板读取失败：${(e as Error).message}`));
    },
    [nodes, links, roles, name, saveDir],
  );

  const onResize = useCallback(
    (id: string, size: [number, number], pos: [number, number]) => {
      // 角色区域不许互相压：缩放后压上了就退回原尺寸 / 原位置
      const hit = isNamespaceNode(
        nodes.find((n) => n.id === id) ?? ({ type: "" } as CardNodeModel),
      )
        ? roleBoxCollisions(nodes, id, pos, size)
        : [];
      if (hit.length) {
        const old = nodes.find((n) => n.id === id);
        if (old) {
          rf.updateNode(id, {
            position: { x: old.pos[0], y: old.pos[1] },
            ...(old.size ? { width: old.size[0], height: old.size[1] } : {}),
          });
        }
        setToast("角色区域不许互相压：这次缩放已撤销");
        return;
      }
      apply((s) => ({
        ...s,
        nodes: s.nodes.map((n) =>
          n.id === id ? { ...n, size, pos, resizing: false } : n,
        ),
      }));
    },
    [apply, nodes, rf],
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

  /** 折叠 / 展开卡片（只显示卡片类型）。界面状态：写进工程 JSON，不进求值载荷。 */
  const toggleCollapse = useCallback(
    (id: string) => {
      apply((s) => ({
        ...s,
        nodes: s.nodes.map((n) => (n.id === id ? { ...n, collapsed: !n.collapsed } : n)),
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
    if (spec.vars_card) {
      const shown = node.fields.show_vars !== false;
      items.push({
        label: shown ? "隐藏变量值" : "显示变量值",
        onClick: () => onField(menu.id, "show_vars", !shown),
      });
    }
    if (spec.role_card) {
      items.push({
        label: spec.weapon_card ? "设置武器名…" : "设置角色名…",
        onClick: () => setRoleNameDialog(menu.id),
      });
      // 复制这个域（含域内卡片与连线）：等价于"只选中它再 Ctrl+C"（同样写系统剪贴板）
      items.push({
        label: spec.weapon_card ? "复制武器域" : "复制角色域",
        onClick: () => copyCards(collectClipboard(
          nodes.map((n) => ({ ...n, selected: n.id === menu.id })),
          links,
        )),
      });
      if (!spec.weapon_card) {
        items.push({ label: "角色面板…", onClick: () => setPanelDialog(menu.id) });
        // 一键藏起区域内的卡片：藏完这只剩一张最小的牌子（再次右键点回来）
        const hiddenNow = cardsHidden(node);
        const count = cardsInside(nodes, menu.id);
        // 区域内卡片连到区域外 → 拒绝隐藏（否则那条线只剩半截）
        const blockers = hiddenNow ? [] : cardsBlockingHide(nodes, links, menu.id);
        const blockedNames = blockers.map((bid) => {
          const n = nodes.find((x) => x.id === bid);
          if (!n) return bid;
          const cardName = String(n.fields.card_name ?? "").trim();
          const typeLabel = schema.nodeTypes[n.type]?.label ?? n.type;
          return cardName ? `${cardName}（${typeLabel}）` : typeLabel;
        });
        items.push({
          label: hiddenNow
            ? `显示区域内的卡片${count ? `（${count} 张）` : ""}`
            : `隐藏区域内的卡片${count ? `（${count} 张）` : ""}`,
          // 有跨区域连线时不给点：鼠标悬停能看到是哪几张卡连到外面
          disabled: blockedNames.length > 0,
          title: blockedNames.length
            ? `区域内的卡片和区域外有连线（${blockedNames.join("、")}），先断开再隐藏`
            : undefined,
          onClick: () =>
            // 一个动作同时切「卡片隐藏」与「容器折叠 / 展开」（见 toggleRoleCardsHidden）
            apply((s) => ({ ...s, nodes: toggleRoleCardsHidden(s.nodes, menu.id) })),
        });
      }
    } else {
      items.push({ label: "命名卡片…", onClick: () => setNameDialog(menu.id) });
    }
    items.push({
      label: node.collapsed ? "展开卡片" : "折叠卡片",
      onClick: () => toggleCollapse(menu.id),
    });
    items.push({ label: "删除卡片", danger: true, onClick: () => removeNode(menu.id) });
    return items;
  }, [menu, nodes, links, schema, results, copyNodeValue, removeNode, setFontSize, setResultVars,
      toggleCollapse, onField, setRoleNameDialog, setPanelDialog, setNameDialog, apply]);

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
      // 复制卡片 / 域（Ctrl+C）与粘贴（Ctrl+V）：输入框里让浏览器自己处理
      if (mod && !typing && e.key.toLowerCase() === "c") {
        if (!e.shiftKey) {
          e.preventDefault();
          doCopyCards();
          return;
        }
      }
      if (mod && e.shiftKey && e.key.toLowerCase() === "c" && !typing) {
        e.preventDefault();
        doCopyValues();
        return;
      }
      if (mod && !typing && e.key.toLowerCase() === "v") {
        e.preventDefault();
        doPasteCards();
        return;
      }
      if (e.key === "Escape" && !typing && !showHelp) clearSelection();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [history, clearSelection, selectAll, showHelp, doSave,
      doCopyCards, doCopyValues, doPasteCards]);

  // -- 渲染 ---------------------------------------------------------------
  // 角色容器排在最前面 → React Flow 按数组顺序决定叠放，容器才会画在卡片**下面**
  const orderedNodes = useMemo(
    () => [...nodes].sort((a, b) => Number(b.type === "role") - Number(a.type === "role")),
    [nodes],
  );
  /** 一键隐藏区域内卡片：这些卡片（以及它们参与的连线）不渲染 */
  const hiddenCards = useMemo(() => hiddenCardsFor(nodes), [nodes]);
  const rfNodes = useMemo<CardRFNode[]>(
    () =>
      orderedNodes.map((n) => {
        const roleBuffRows = (roleNode: CardNodeModel) => {
          const roleName = String(roleNode.fields.role_name ?? "").trim();
          const s = roleName ? evaluation.data?.buffStats?.[roleName] : undefined;
          return { out: s?.out ?? [], in: s?.in ?? [] };
        };
        // 画布上的「面板」：显示哪几项由 panel_show 控制；留空 = 只显示已有值的那些
        const rolePanelRows = (roleNode: CardNodeModel) => {
          const roleName = String(roleNode.fields.role_name ?? "").trim();
          const data0 = evaluation.data;
          if (!roleName || !data0) return [];
          const values = new Map(data0.variables.map((v) => [v.name, v.text]));
          const incoming = new Map(
            (data0.buffStats?.[roleName]?.in ?? []).map((r) => [r.macro, r.value]),
          );
          const shown = parsePanelShow(String(roleNode.fields.panel_show ?? ""));
          return schema.panelMacros
            .map((m) => ({
              key: m.key,
              label: m.label,
              value: values.get(`${roleName}::${m.key}`) ?? "",
              incoming: incoming.get(m.key) ?? 0,
            }))
            .filter((r) => (shown.length ? shown.includes(r.key) : r.value !== ""));
        };
        const data: CardData = {
          node: n,
          spec: schema.nodeTypes[n.type],
          result: results[n.id] ?? null,
          fontSize: n.font_size ?? 0,
          table: tableFor(n, schema, results),
          role: roles[n.id] ?? "",
          // 「外部域」补全要用同一个基准目录（与求值解析相对路径一致）
          baseDir: saveDir,
          // 变量卡编辑器里一起高亮的词（面板宏名，来自 schema）
          macros: schema.panelMacros.map((m) => m.key),
          // 角色卡：左上角标签上方显示"出入度"（给出去/收进来的拐）
          roleBuffs: isNamespaceNode(n) ? roleBuffRows(n) : undefined,
          rolePanel: isPanelNode(n) ? rolePanelRows(n) : undefined,
          onField,
          onDelete: removeNode,
          onResize,
          onCellPanel,
          onMenu: (id, kind, ev) => setMenu({ id, kind, x: ev.clientX, y: ev.clientY }),
          onCopy,
        };
        let style: CSSProperties | undefined;
        if (!n.resizing) {
          if (n.collapsed) {
            // 折叠后高度由内容（只剩标题栏）决定，只保留用户拖出来的宽度
            style = n.size ? { width: n.size[0] } : undefined;
          } else if (n.size) {
            style = { width: n.size[0], height: n.size[1] };
          }
        }
        if (isNamespaceNode(n)) {
          // 角色容器只是**背景标记**（一块虚线区域 + 一条可拖的标签）：
          // 区域本身不该吃鼠标事件，否则鼠标落在上面会命中节点（光标变抓手）也拖不出框选。
          // 写在**内联样式**上最稳：不受任何 CSS 优先级/顺序影响（样式表那两条只是文档与兜底）。
          style = { ...(style ?? {}), pointerEvents: "none" };
          if (n.collapsed && !n.resizing) {
            // 折叠成**最小**（一键隐藏后只剩一张牌子）：撤掉存下来的高度，
            // 否则那块虚线区域仍占着原来的大小，看着像没折叠
            style = { ...style, height: "auto", minHeight: 0 };
          }
        }
        return {
          id: n.id,
          type: "card" as const,
          position: { x: n.pos[0], y: n.pos[1] },
          data,
          // 拖动中压到别的角色区域 → 这个框描红（红框就是碰撞箱，见 types.ts 的 colliding）
          style: n.colliding ? { ...(style ?? {}), ...ROLE_BOX_COLLIDING_STYLE } : style,
          // 一键隐藏区域内卡片：只是不渲染（模型/工程 JSON 里都还在）
          hidden: hiddenCards.has(n.id),
          selected: Boolean(n.selected),
          measured: n.measured,
          // 角色容器：整个节点不吃鼠标事件（见 styles.css 的 .node-role-box）——
          // 否则鼠标落在面板上时命中节点，光标变成抓手，也拖不出框选。
          className: isNamespaceNode(n) ? "node-role-box" : undefined,
          // 只有标题栏能拖动（见 model.ts 的说明）
          dragHandle: CARD_DRAG_HANDLE,
        };
      }),
    [orderedNodes, schema, results, roles, onField, removeNode, onCopy, onResize, onCellPanel,
     evaluation.data, hiddenCards, revision],
  );

  const rfEdges = useMemo<CardRFEdge[]>(
    () =>
      links
        // 端点在「隐藏区域内卡片」里的连线一起藏起来（否则箭头悬在半空）
        .filter((l) => !hiddenCards.has(l.src) && !hiddenCards.has(l.dst))
        // 「显示域间箭头」开关关掉时，拐力箭头不渲染（只影响显示：连线仍在工程里，
        // 拐力照旧参与求值）
        .filter((l) => showDomainArrows || !isBuffPairCb(l.src, l.dst))
        .map((l) => {
          const id = edgeId(l.src, l.dst, l.port);
          const buff = isBuffPairCb(l.src, l.dst);
          return {
            id,
            type: "card" as const,
            source: l.src,
            target: l.dst,
            sourceHandle: "out",
          targetHandle: `in-${l.port}`,
          selected: selectedEdge === id,
          interactionWidth: 18,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 14,
            height: 14,
            // 拐力箭头：浅蓝（与伤害连线的主蓝区分；用户要求不用虚线）
            color: "#7fa8cc",
          },
            data: {
              src: l.src,
              dst: l.dst,
              port: l.port,
              buff,
              dim: Boolean(hoverId && l.src !== hoverId && l.dst !== hoverId),
              onDelete: removeLink,
            },
          };
        }),
    [links, selectedEdge, hoverId, removeLink, isBuffPairCb, hiddenCards, showDomainArrows],
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
        saveDir={saveDir}
        staleHint={staleHint}
        buildTime={buildTime}
        dirty={dirty}
        canUndo={history.canUndo}
        canRedo={history.canRedo}
        onUndo={history.undo}
        onRedo={history.redo}
        onSave={doSave}
        onOpen={() => void doOpen()}
        onExport={() => void doExport()}
        onNewProject={() => setNewDialog(true)}
        onHelp={() => setShowHelp(true)}
        zoom={liveZoom}
        onZoomIn={() => rf.zoomIn({ duration: 120 })}
        onZoomOut={() => rf.zoomOut({ duration: 120 })}
        onZoomReset={() => rf.zoomTo(1, { duration: 120 })}
        onFit={() => rf.fitView({ padding: 0.15, duration: 200 })}
        boxSelectDomains={boxSelectDomains}
        // 切换时不弹 toast（用户要求：开关自己高亮就够，别再在下方出提示）
        onToggleBoxSelectDomains={() => setBoxSelectDomains((v) => !v)}
        showDomainArrows={showDomainArrows}
        onToggleShowDomainArrows={() => setShowDomainArrows((v) => !v)}
        status={status}
      />

      <div className="main">
        <Sidebar
          schema={schema}
          selectedCount={selectedCount}
          onAdd={addNode}
          onPreset={onPreset}
          onAlign={onAlign}
          onClearSelection={clearSelection}
        />
        {/* 画布容器：顺手记下鼠标屏幕坐标 —— 粘贴时换算成流坐标，卡片就出现在鼠标附近 */}
        <div
          className="canvas"
          data-testid="canvas"
          onMouseMove={(e) => {
            pointer.current = { x: e.clientX, y: e.clientY };
          }}
        >
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
            // 框选期间：忽略角色容器的选中变化（它是一大块面板，否则框选必把它卷进来）
            onSelectionStart={() => {
              boxSelecting.current = true;
            }}
            onSelectionEnd={() => {
              boxSelecting.current = false;
            }}
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
            <CanvasWatermark name={name} />
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

      {cellPanelData ? (
        <MatrixPanelDialog data={cellPanelData} onClose={() => setCellPanelData(null)} />
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

      {nameDialog ? (
        <NameCardDialog
          initial={String(nodes.find((n) => n.id === nameDialog)?.fields.card_name ?? "")}
          title={schema.nodeTypes[nodes.find((n) => n.id === nameDialog)?.type ?? ""]?.title ?? ""}
          role={roles[nameDialog] ?? ""}
          onSave={(name) => {
            onField(nameDialog, "card_name", name);
            setNameDialog(null);
          }}
          onClose={() => setNameDialog(null)}
        />
      ) : null}

      {roleNameDialog ? (() => {
        const dialogNode = nodes.find((n) => n.id === roleNameDialog);
        // 武器与角色是同一套命名空间，但弹窗标题/标签要分开（用户要求）
        const kind: "角色" | "武器" =
          schema.nodeTypes[dialogNode?.type ?? ""]?.weapon_card ? "武器" : "角色";
        return (
          <RoleNameDialog
            initialName={String(dialogNode?.fields.role_name ?? "").trim()}
            kind={kind}
            check={(name) => roleNameError(nodes, name, roleNameDialog, kind)}
            onSave={(name) => {
              onField(roleNameDialog, "role_name", name);
              setRoleNameDialog(null);
            }}
            onClose={() => setRoleNameDialog(null)}
          />
        );
      })() : null}

      {panelDialog ? (() => {
        const node = nodes.find((n) => n.id === panelDialog);
        const roleName = String(node?.fields.role_name ?? "").trim();
        const keys = schema.panelMacros.map((m) => m.key);
        const stats = roleName ? evaluation.data?.buffStats?.[roleName] : undefined;
        const parsed = parseRolePanel(
          String(node?.fields.panel ?? ""),
          keys,
          schema.panelCustomPattern,
        );
        return (
          <RolePanelDialog
            title={roleName || "未命名"}
            macros={schema.panelMacros}
            initial={parsed.values}
            initialCustom={parsed.custom}
            customPattern={schema.panelCustomPattern}
            initialShow={parsePanelShow(String(node?.fields.panel_show ?? ""))}
            stats={stats}
            onSave={(values, show, custom) => {
              onField(panelDialog, "panel", formatRolePanel(values, keys, custom));
              onField(panelDialog, "panel_show", formatPanelShow(show));
              setPanelDialog(null);
            }}
            onClose={() => setPanelDialog(null)}
          />
        );
      })() : null}

      {newDialog ? (
        <NewProjectDialog
          initialName={name}
          cardCount={nodes.length}
          onCreate={doNewProject}
          onClose={() => setNewDialog(false)}
        />
      ) : null}

      {showHelp ? (
        <HelpDialog text={help.text} sections={help.sections} onClose={() => setShowHelp(false)} />
      ) : null}

      {toast ? (
        <button
          type="button"
          className="toast"
          data-testid="toast"
          title="点一下立刻关掉（不点的话 5 秒后自动消失）"
          onClick={() => setToast("")}
        >
          {toast}
        </button>
      ) : null}
    </div>
  );
}

/** 从工程文件路径里取工程名（去掉目录与 .json 后缀）；取不到就返回空串。 */
function projectNameFromPath(path?: string): string {
  const raw = String(path ?? "").trim();
  if (!raw) return "";
  const base = raw.split(/[\\/]/).pop() ?? "";
  return base.replace(/\.json$/i, "").trim();
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
  if (spec.table === "matrix") {
    // 后端已经把整张表算好了（第一行是表头）：见 genshin_dmg/matrix.py
    const rows = results[node.id]?.rows ?? [];
    return { header: rows[0] ?? ["行 \\ 列"], rows: rows.slice(1) };
  }
  return {
    header: schema.tables.vars.header,
    rows: results[node.id]?.rows ?? [["（暂无变量）", ""]],
  };
}
