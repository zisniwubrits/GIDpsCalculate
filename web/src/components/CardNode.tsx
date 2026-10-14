/**
 * 画布上的一张卡片。
 *
 * 卡片长什么样完全由后端 schema 驱动：字段控件按 `kind` 渲染，
 * 结果文案（本卡系数 ｜ 输出）直接用后端返回的 `display`，保证与 Python 侧完全一致。
 */
import { Handle, NodeResizer, Position, type Node, type NodeProps } from "@xyflow/react";
import { memo, useCallback, type CSSProperties } from "react";
import type { BuffStatRow, CardNode, FieldSpec, FieldValue, NodeResult, NodeTypeSpec } from "../types";
import DataTable from "./DataTable";

export interface CardData extends Record<string, unknown> {
  node: CardNode;
  spec: NodeTypeSpec;
  result: NodeResult | null;
  fontSize: number;
  /** 表格类卡片的内容（const 静态 / vartable 动态） */
  table: { header: string[]; rows: string[][] } | null;
  /** 这张卡片属于哪个「角色」命名空间（由画布上的容器面板按位置推导，空 = 不属于任何角色） */
  role: string;
  /** 只对角色卡有意义：这个命名空间**给出去的拐**（OUT）与**收到的拐**（IN） */
  roleBuffs?: { out: BuffStatRow[]; in: BuffStatRow[] };
  /** 只对角色卡有意义：画布上面板要显示的行（宏名 / 中文名 / 生效值 / 收到的拐） */
  rolePanel?: { key: string; label: string; value: string; incoming: number }[];
  onField: (id: string, key: string, value: FieldValue) => void;
  onDelete: (id: string) => void;
  /** 拖动缩放手柄结束后把最终尺寸（含左上角坐标变化）写回模型 */
  onResize: (id: string, size: [number, number], pos: [number, number]) => void;
  onMenu: (id: string, kind: MenuKind, ev: { clientX: number; clientY: number }) => void;
  onCopy: (id: string) => void;
}

export type MenuKind = "result" | "font" | "card";
export type CardRFNode = Node<CardData, "card">;

// ------------------------------------------------------------ 拐力端口的位置
// 一个入度 + 一个出度，都以**容器宽度百分比**定（用户口径：就是容器 50% 那条线，
// 左右各一个 —— 入度 48%、出度 52%，分居 50% 两侧）：
//   * 写百分比（不写像素）时卡片/区域多宽都跟着走，不会因为区域被拉宽而跑偏；
//   * 位置固定，不随"收到几份拐"变化 —— 多来源的箭头**都汇聚到同一个入度点**上
//     （用户口径："多个箭头可以往一个点指"）。
// 纵向由 styles.css 的 .role-port-* 定（负偏移 = 抬到卡片上边缘之上）。
/** 入度端口的水平位置（50% 那条线左侧一档） */
export const ROLE_PORT_IN_LEFT = "48%";
/** 出度端口的水平位置（50% 那条线右侧一档） */
export const ROLE_PORT_OUT_LEFT = "52%";
/** 正好落在 50% 那条线上（武器只有出度一个端口，就放这儿） */
export const ROLE_PORT_CENTER = "50%";

/**
 * 拖动角色区域**压到别的区域**时给它的临时样式（描红）。
 *
 * 为什么需要：角色区域框（560×380）比看得见的内容（只有一块 26px 高的牌子）
 * 大十几倍，"压上了"在画面上看不出来，用户只会觉得程序在乱报不合法。
 * 这个红框就是把「碰撞箱」显形：拖动中一旦压上，框子当场变红。
 * 由 App 在拖动过程中通过 `rf.updateNode(id, { style })` 挂上 / 摘掉。
 */
export const ROLE_BOX_COLLIDING_STYLE: CSSProperties = {
  outline: "2px solid #d9534f",
  outlineOffset: "-2px",
  background: "rgba(217, 83, 79, 0.06)",
};

function FieldControl({
  field,
  value,
  onChange,
  bare = false,
}: {
  field: FieldSpec;
  value: FieldValue;
  onChange: (v: FieldValue) => void;
  /** 便签式卡片：不画标签、控件不带边框（由 schema 的 bare 字段决定） */
  bare?: boolean;
}) {
  const label = bare ? null : <span className="f-label">{field.label}</span>;
  switch (field.kind) {
    case "check":
      return (
        <label className="f-check">
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
          />
          <span>{field.label}</span>
        </label>
      );
    case "combo": {
      const options = field.options ?? [];
      const current = String(value ?? "");
      const list = options.includes(current) || !current ? options : [current, ...options];
      return (
        <>
          {label}
          <select
            className="f-input"
            value={current}
            onChange={(e) => onChange(e.target.value)}
            title={current}
          >
            {list.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </>
      );
    }
    case "textbox":
      return (
        <>
          {label}
          <textarea
            className={`f-input f-area${bare ? " f-bare" : ""}`}
            value={String(value ?? "")}
            rows={bare ? undefined : field.key === "content" ? 4 : 3}
            spellCheck={false}
            onChange={(e) => onChange(e.target.value)}
          />
        </>
      );
    case "pct":
      return (
        <>
          <span className="f-label">{field.label}</span>
          <span className="f-wrap">
            <input
              className="f-input"
              value={String(value ?? "")}
              spellCheck={false}
              onChange={(e) => onChange(e.target.value)}
            />
            <span className="f-suffix">%</span>
          </span>
        </>
      );
    default:
      return (
        <>
          <span className="f-label">{field.label}</span>
          <input
            className="f-input"
            value={String(value ?? "")}
            spellCheck={false}
            onChange={(e) => onChange(e.target.value)}
          />
        </>
      );
  }
}

function CardNodeView({ id, data, selected }: NodeProps<CardRFNode>) {
  const { node, spec, result, fontSize, table } = data;
  // 角色卡片是个例外：它没有伤害端口，但要一对**拐力端口** ——
  // 从源角色标签拖到目标角色标签，就等于把这个角色的面板值拐给对面。
  const isRole = Boolean(spec.role_card);
  /** 武器：同属命名空间容器，但只输出拐力（没有输入端口、没有面板） */
  const isWeapon = Boolean(spec.weapon_card);
  /** 拐力端口的悬停说明：带上这个命名空间已经收到/给出的拐（明细看「角色面板」弹窗） */
  const buffIn = data.roleBuffs?.in ?? [];
  const buffOut = data.roleBuffs?.out ?? [];
  const inTitle = buffIn.length
    ? `收到的拐：${buffIn.map((r) => `${r.role} ${r.label} ${r.value}`).join("；")}`
    : "收到的拐：把别的角色的拐力端口拖到这里";
  const outTitle = buffOut.length
    ? `给出去的拐：${buffOut.map((r) => `${r.label} ${r.value} → ${r.role}`).join("；")}`
    : "拐力：把本角色**声明过的 out:: 值**拐给对面（在「角色面板…」里加一行自定义对外项）";
  const hasInput = (isRole && !isWeapon) || (!spec.isolated && !isRole && spec.inputs > 0);
  // sink 卡片（「赋值变量」）只有输入端口：它不参与结果链，只把上游值记到变量表
  const hasOutput = isRole || (!spec.isolated && !spec.no_output && !spec.sink);
  /** 折叠状态：只显示卡片类型（标题栏），字段区与底部输出都收起 */
  const collapsed = Boolean(node.collapsed);

  const onField = useCallback(
    (key: string, v: FieldValue) => data.onField(id, key, v),
    [data, id],
  );

  // 标题栏文案：
  //  * 角色容器 → 只显示角色名（用户要求：顶部不要再挂「角色 · 」前缀）
  //  * 计算卡 → 它自己的标题（历史行为）
  //  * 其余 → 卡片类型（命名后的名字另挂徽标，见下面的 card-name-chip）
  const cardName = String(node.fields.card_name ?? "").trim();
  const baseTitle =
    node.type === "calc" ? String(node.fields.title ?? spec.title) || spec.title : spec.title;
  const title = collapsed
    ? spec.label
    : spec.role_card
      ? String(node.fields.role_name ?? "").trim() || "未命名"
      : baseTitle;

  // 角色卡没有可见字段（角色名改成右键「设置角色名…」了）→ 不渲染空的卡片体
  const body =
    collapsed || (spec.fields.length === 0 && !spec.table) ? null : (
    <div
      className={`card-body${spec.bare ? " card-body-bare" : ""}${
        spec.table ? " card-body-table" : ""
      }`}
    >
      {spec.table && table ? (
        <DataTable
          header={table.header}
          rows={table.rows}
          mono={spec.table === "vars"}
          testId={`table-${spec.table}-${id}`}
        />
      ) : null}
      {spec.fields.map((f) => (
        <div className={`f-row${spec.bare ? " f-row-bare" : ""}`} key={f.key}>
          <FieldControl
            field={f}
            value={node.fields[f.key]}
            onChange={(v) => onField(f.key, v)}
            bare={spec.bare}
          />
        </div>
      ))}
    </div>
  );

  const footer = collapsed ? null : (() => {
    if (spec.no_output) return null;
    if (node.type === "var") {
      return (
        <div className="card-foot">
          {result?.varsText && node.fields.show_vars !== false ? (
        <span className="foot-text">{result.varsText}</span>
      ) : null}
        </div>
      );
    }
    if (!result) {
      return (
        <div className="card-foot">
          <span className="foot-dim">计算中…</span>
        </div>
      );
    }
    if (result.error) {
      return (
        <div className="card-foot foot-error">
          <span>输出: 错误({result.error})</span>
        </div>
      );
    }
    return (
      <div className={`card-foot${node.type === "result" ? " foot-result" : ""}`}>
        <span className="foot-text">{result.display || "—"}</span>
        {/* 可见标注：这些字段是"留空→吃角色面板"的；本角色还收了拐 */}
        {result.panelFields?.length ? (
          <span
            className="foot-chip"
            data-testid={`panel-mark-${id}`}
            title={`这些字段留空，值来自角色面板：${result.panelFields.join("、")}`}
          >
            含面板
          </span>
        ) : null}
        {result.buffed ? (
          <span
            className="foot-chip foot-chip-buff"
            data-testid={`buff-mark-${id}`}
            title="本角色收到了别的角色拐过来的面板加成"
          >
            含拐
          </span>
        ) : null}
        {spec.copyable ? (
          <button
            type="button"
            className="foot-copy"
            title="复制输出数值"
            onClick={() => data.onCopy(id)}
          >
            复制
          </button>
        ) : null}
      </div>
    );
  })();

  const handles = [];
  if (isRole) {
    // 角色卡的拐力端口：**入度一个点、出度一个点**，都在卡片顶部居中那一带。
    //
    // 为什么只有一个入度（用户要求"改成多个箭头可以往一个点指"）：原来按"几个来源
    // 就摆几个端口"（3 个起步），可多端口会随来源数量重新展开、位置也跟着变，
    // 箭头落点看起来就总在错位。收成一个点之后，多来源的箭头都汇聚到同一个点上，
    // 既不会再错位，也不用再维护"端口个数"这套逻辑。
    //
    // 横向仍是**百分比**（相对"整个角色节点"的宽度）—— 只有一个端口、位置固定，
    // 百分比才安全；之前的多端口用百分比会按 560px 的节点宽度展开，跑到区域正中。
    const inCount = isWeapon ? 0 : 1;
    for (let i = 0; i < inCount; i += 1) {
      handles.push(
        <Handle
          key={`in-${i}`}
          id={`in-${i}`}
          type="target"
          position={Position.Top}
          className="port port-in role-port-in"
          style={{ left: ROLE_PORT_IN_LEFT }}
          title={inTitle}
        />,
      );
    }
    // 出度：角色**和武器**都对外提供拐力（武器是"只出不进"，所以它只有这个端口）。
    //
    // 注意这里**不能**写 `if (!isWeapon)` —— 那会把武器的出度端口也一起砍掉，
    // 武器就彻底没有端口了（用户报过"武器卡片的输出端口看不见"）。
    // 位置：武器只有这一个端口，就放在 50% 那条线上（用户要求）；
    // 角色的出度与入度成对，所以仍在 52%（50% 右侧一档）。
    handles.push(
      <Handle
        key="out"
        id="out"
        type="source"
        position={Position.Top}
        className="port port-out role-port-out"
        style={{ left: isWeapon ? ROLE_PORT_CENTER : ROLE_PORT_OUT_LEFT }}
        title={outTitle}
      />,
    );
  } else {
    if (hasInput) {
      const n = Math.max(1, node.inputs);
      for (let i = 0; i < n; i += 1) {
        handles.push(
          <Handle
            key={`in-${i}`}
            id={`in-${i}`}
            type="target"
            position={Position.Left}
            style={{ top: `${((i + 1) / (n + 1)) * 100}%` }}
            className="port port-in"
          />,
        );
      }
    }
    if (hasOutput && !spec.no_output) {
      handles.push(
        <Handle
          key="out"
          id="out"
          type="source"
          position={Position.Right}
          className="port port-out"
        />,
      );
    }
  }

  return (
    <>
      <NodeResizer
        isVisible={Boolean(selected) && !collapsed}
        minWidth={160}
        minHeight={90}
        lineClassName="resize-line"
        handleClassName="resize-handle"
        onResizeEnd={(_event, params) => {
          // 显式把最终尺寸写回模型：否则卡片高度只存在于 React Flow 内部，
          // 下一次重渲染会用旧尺寸覆盖回去，表现为「纵向缩放不动」。
          data.onResize(
            id,
            [Math.round(params.width), Math.round(params.height)],
            [Math.round(params.x), Math.round(params.y)],
          );
        }}
      />
      <div
        className={`card${selected ? " card-sel" : ""}${node.type === "result" ? " card-result" : ""}${collapsed ? " card-collapsed" : ""}${spec.role_card ? " card-role-box" : ""}${node.colliding ? " card-colliding" : ""}`}
        style={fontSize ? { fontSize: `${fontSize}px` } : undefined}
        data-testid={`card-${id}`}
        data-type={node.type}
        data-collapsed={collapsed ? "1" : undefined}
        data-colliding={node.colliding ? "1" : undefined}
      >
        <div
          className="card-head"
          onContextMenu={(e) => {
            e.preventDefault();
            const kind: MenuKind = spec.ctx_menu
              ? "result"
              : spec.font_menu
                ? "font"
                : "card";
            data.onMenu(id, kind, { clientX: e.clientX, clientY: e.clientY });
          }}
        >
          <span className="card-title" title={spec.title}>
            {title}
          </span>
          {/* 命名空间徽标：只显示**名字本身**，不带尾随 `::`
              —— `::` 后面没有字段时没必要显示（用户要求）；完整用法写在 title 里 */}
          {cardName && !collapsed && node.type !== "calc" ? (
            <span
              className="card-name-chip"
              title={`引用这张卡的输出：${cardName}（期望值）／ ${cardName}::暴击 ／ ${cardName}::未暴击`}
            >
              {cardName}
            </span>
          ) : null}
          {data.role && !collapsed ? (
            <span
              className="card-role-chip"
              title={`属于角色「${data.role}」：其中的变量写作 ${data.role}::变量名`}
            >
              {data.role}
            </span>
          ) : null}
          <button
            type="button"
            className="card-x nodrag"
            title="删除卡片"
            onClick={() => data.onDelete(id)}
          >
            ✕
          </button>
        </div>
        {/* 角色标记的「面板」：显示在左上角标记牌**下方**（画布上就能看到属性），
            显示哪几项由右键「角色面板…」里的勾选控制；只读，不吃鼠标事件 */}
        {spec.role_card && !isWeapon && !collapsed && data.rolePanel?.length ? (
          <div className="role-panel" data-testid={`role-panel-${id}`}>
            {data.rolePanel.map((r) => (
              <div
                className="rp-row"
                key={r.key}
                title={
                  r.incoming
                    ? `${r.label}：自身 + 收到的 ${r.incoming}`
                    : `${r.label}（${r.key}）`
                }
              >
                <span className="rp-key">{r.key}</span>
                <span className={`rp-val${r.incoming ? " rp-buffed" : ""}`}>{r.value}</span>
              </div>
            ))}
          </div>
        ) : null}
        {body}
        {footer}
      </div>
      {handles}
    </>
  );
}

export default memo(CardNodeView);
