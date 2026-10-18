/**
 * 角色面板的公共零件（「角色面板」弹窗与「域对照表」右键面板共用）。
 *
 * 为什么单独抽出来：两处的面板长得要**一模一样**（用户要求），
 * 以前域对照表用的是另画的一套表格，样式与角色面板对不上；
 * 现在宏表的表头 / 行结构 / 拐力列表都只有这一份实现。
 */
import type { ReactNode } from "react";

/** 面板宏（来自 schema）：key / 中文名 / 喂给哪张卡 */
export interface PanelMacro {
  key: string;
  label: string;
  feed?: string;
}

export interface PanelMacroGridProps {
  macros: PanelMacro[];
  /** 当前值 {宏: 值文本} */
  values: Record<string, string>;
  /** 画布面板要显示哪些宏（可编辑模式下用） */
  show?: string[];
  onChangeValue?: (key: string, next: string) => void;
  onToggleShow?: (key: string, on: boolean) => void;
  /** 每项"收到的拐"（只读模式下显示 +N） */
  incoming?: Record<string, number>;
  /** 只读：值显示成文字，不出现输入框 / 勾选框 */
  readOnly?: boolean;
  testIdPrefix?: string;
  /** 表格下面的额外内容（自定义对外项之类） */
  children?: ReactNode;
}

/**
 * 面板宏表：`宏 | 属性 | 值 | 收到 | 喂给哪张卡 | 显示`。
 *
 * 只读模式去掉"显示"列与输入框 —— 域对照表右键面板用它。
 */
export function PanelMacroGrid({
  macros,
  values,
  show = [],
  onChangeValue,
  onToggleShow,
  incoming,
  readOnly = false,
  testIdPrefix = "panel",
  children,
}: PanelMacroGridProps) {
  const hasIncoming = Boolean(incoming) && !readOnly;
  return (
    <div className={`panel-macro-grid${readOnly ? " panel-macro-readonly" : ""}`}>
      <div className="panel-macro-head">
        <span className="pm-key">宏</span>
        <span className="pm-label">属性</span>
        <span>值{readOnly ? "" : "（可写算式/变量）"}</span>
        {readOnly && incoming ? <span className="pm-in">收到</span> : null}
        {readOnly ? null : <span className="pm-feed">喂给哪张卡</span>}
        {readOnly ? null : (
          <span className="pm-show-head" title="勾选后显示在画布的角色面板上">
            显示
          </span>
        )}
      </div>
      {macros.map((m) => (
        <div className="panel-macro-row" key={m.key}>
          <span className="pm-key">{m.key}</span>
          <span className="pm-label">{m.label}</span>
          {readOnly ? (
            <span className="pm-value" data-testid={`${testIdPrefix}-${m.key}`}>
              {values[m.key] || "—"}
            </span>
          ) : (
            <input
              value={values[m.key] ?? ""}
              data-testid={`${testIdPrefix}-${m.key}`}
              placeholder="留空 = 不启用"
              onChange={(e) => onChangeValue?.(m.key, e.target.value)}
            />
          )}
          {readOnly && incoming ? (
            <span className="pm-in num" data-testid={`${testIdPrefix}-in-${m.key}`}>
              {incoming[m.key] ? `+${incoming[m.key]}` : ""}
            </span>
          ) : null}
          {readOnly ? null : (
            <span className="pm-feed" title={m.feed}>
              {m.feed ?? ""}
            </span>
          )}
          {readOnly ? null : (
            <input
              type="checkbox"
              className="pm-show"
              data-testid={`${testIdPrefix}-show-${m.key}`}
              title="在画布的角色面板上显示这一项"
              checked={show.includes(m.key)}
              onChange={(e) => onToggleShow?.(m.key, e.target.checked)}
            />
          )}
        </div>
      ))}
      {hasIncoming ? null : null}
      {children}
    </div>
  );
}

/** 拐力列表（给出去 / 收到）：`名字 数值 来源角色` */
export function BuffRows({
  list,
  emptyTestId = "buff-empty",
}: {
  list: { macro: string; label: string; value: number; role?: string }[];
  emptyTestId?: string;
}) {
  if (!list.length) {
    return (
      <p className="modal-hint" data-testid={emptyTestId}>
        （无）
      </p>
    );
  }
  return (
    <ul className="buff-list" data-testid="buff-list">
      {list.map((r, i) => (
        <li key={`${r.macro}-${r.role ?? ""}-${i}`}>
          <b>{r.label}</b>
          <span className="buff-val">{r.value}</span>
          <span className="dim">{r.role ?? ""}</span>
        </li>
      ))}
    </ul>
  );
}


/**
 * 词条来源统计（只读）：某个属性的值是怎么来的。
 *
 * * 自身：`own::atk_pct = 24+27.6+34.8*2+46.6` 这种写法按项列出（原样 + 数值）；
 * * 拐力：哪张卡 / 哪个域给了多少。
 *
 * 用 `.buff-list` 的样式，与「角色面板」的 OUT/IN 列表看起来一致。
 */
export interface PanelSources {
  label: string;
  /** 自身词条逐项 */
  selfTerms: { text: string; value: number | null }[];
  /** 拐力来源 */
  grants: { source: string; value: number }[];
}

export function SourceRows({ list }: { list: PanelSources[] }) {
  const shown = list.filter((r) => r.selfTerms.length || r.grants.length);
  if (!shown.length) {
    return (
      <p className="modal-hint" data-testid="source-empty">
        （无）
      </p>
    );
  }
  return (
    <ul className="buff-list" data-testid="source-list">
      {shown.map((row) => (
        <li key={row.label} className="source-row">
          <b>{row.label}</b>
          {row.selfTerms.length ? (
            <span className="source-self" title="自身（该域文件里 own:: 的算式逐项）">
              自身{" "}
              {row.selfTerms
                .map((t) => {
                  if (t.value === null) return t.text;
                  // 纯数字项直接给数值；`34.8*2` 这种算式才把原样也写出来
                  return String(t.value) === t.text.trim()
                    ? String(t.value)
                    : `${t.text}（${t.value}）`;
                })
                .join(" + ")}
            </span>
          ) : null}
          {row.grants.length ? (
            <span className="dim" title="拐力来源">
              拐{" "}
              {row.grants
                .map((g) => `${g.source} +${Number(g.value.toFixed(2))}`)
                .join("、")}
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
