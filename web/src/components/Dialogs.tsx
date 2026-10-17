/**
 * 弹窗：设置结果变量（★结果卡片右键）、F1 教程。
 */
import { useEffect, useRef, useState } from "react";
import {
  DEFAULT_PANEL_CUSTOM_PATTERN,
  nextCustomOutName,
  SUB_OUT,
  validCustomOut,
} from "../model";

export interface ResultVarsDialogProps {
  initial: Record<string, string>;
  labels: { key: string; label: string }[];
  onSave: (values: Record<string, string>) => void;
  onClear: () => void;
  onClose: () => void;
}

export function ResultVarsDialog({
  initial,
  labels,
  onSave,
  onClear,
  onClose,
}: ResultVarsDialogProps) {
  const [values, setValues] = useState<Record<string, string>>({ ...initial });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-mask" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-label="设置结果变量"
        data-testid="result-vars-dialog"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2>设置结果变量</h2>
        {labels.map((f) => (
          <label className="modal-row" key={f.key}>
            <span>{f.label}</span>
            <input
              value={values[f.key] ?? ""}
              data-testid={`var-${f.key}`}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
            />
          </label>
        ))}
        <div className="modal-actions">
          <button type="button" className="danger" onClick={onClear}>
            清除结果变量
          </button>
          <span className="grow" />
          <button type="button" onClick={onClose}>
            取消
          </button>
          <button type="button" className="primary" onClick={() => onSave(values)}>
            确定
          </button>
        </div>
      </div>
    </div>
  );
}

export interface NameCardDialogProps {
  /** 卡片当前的名字（空串 = 未命名） */
  initial: string;
  /** 卡片类型标题（保留给弹窗标题用；说明文字已按用户要求删除） */
  title: string;
  /** 该卡所属角色（空串 = 不属于任何角色） */
  role: string;
  onSave: (name: string) => void;
  onClose: () => void;
}

/**
 * 给卡片起名（右键菜单「命名卡片…」）。
 *
 * 名字只显示在标题栏（`增伤区 · 雷神增伤`），**不占卡片版面**；
 * 命名后可以像变量一样引用这张卡的输出：`卡片名` = 期望值，
 * `卡片名::暴击` / `卡片名::未暴击` 取另外两个分量。
 *
 * 弹窗里只留「输入框 + 按钮」：解释文字与占位示例按用户要求全部删掉（说明在 F1 教程里）。
 */
export function NameCardDialog({
  initial,
  onSave,
  onClose,
}: NameCardDialogProps) {
  const [value, setValue] = useState(initial);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const name = value.trim();

  return (
    <div className="modal-mask" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-label="命名卡片"
        data-testid="name-card-dialog"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2>命名卡片</h2>
        <label className="modal-row">
          <span>卡片名</span>
          <input
            value={value}
            data-testid="card-name-input"
            autoFocus
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onSave(name);
            }}
          />
        </label>
        <div className="modal-actions">
          <span className="grow" />
          <button type="button" onClick={onClose}>
            取消
          </button>
          <button type="button" className="primary" onClick={() => onSave(name)}>
            确定
          </button>
        </div>
      </div>
    </div>
  );
}

export interface RolePanelDialogProps {
  /** 「角色 · 名字」，只用于标题 */
  title: string;
  /** 固定宏词表（来自 schema：key / 中文名 / 喂给哪张卡） */
  macros: { key: string; label: string; feed: string }[];
  /** 当前面板值 {宏: 值文本}；自定义对外项用 `out::名字` 作键 */
  initial: Record<string, string>;
  /** 已有的自定义对外项名字（`out::名字`，按出现顺序） */
  initialCustom: string[];
  /** 自定义对外项名字的规则（schema 的 panelCustomPattern；后端是权威） */
  customPattern?: string;
  /** 画布上那块面板要显示哪些宏（空 = 只显示已有值的） */
  initialShow: string[];
  /** 拐力统计（OUT：给出去多少；IN：收进来多少） */
  stats?: { out: { macro: string; label: string; value: number; role: string }[];
            in: { macro: string; label: string; value: number; role: string }[] };
  onSave: (values: Record<string, string>, show: string[], custom: string[]) => void;
  onClose: () => void;
}

/**
 * 角色面板（右键角色标签打开）：上面是**可编辑的宏表**，下面是**拐力统计**。
 *
 * 「面板」是原神黑话里的角色属性表：面板项就是本角色命名空间里的变量，
 * 卡片字段留空时会用它们兜底；拖拐力箭头时也是把这张表加到目标角色的同名项上。
 *
 * 除固定词表外，还能加**自定义对外项**（`out::名字 = 值`）：本角色没有这个属性，
 * 但要把一份拐力给出去（"面板外拐"）。名字规则由后端给（customPattern）。
 */
export function RolePanelDialog({
  title,
  macros,
  initial,
  initialCustom,
  customPattern = DEFAULT_PANEL_CUSTOM_PATTERN,
  initialShow,
  stats,
  onSave,
  onClose,
}: RolePanelDialogProps) {
  const [values, setValues] = useState<Record<string, string>>({ ...initial });
  const [custom, setCustom] = useState<string[]>([...initialCustom]);
  const [show, setShow] = useState<string[]>([...initialShow]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  /** 自定义对外项在 values 里的键 */
  const customKey = (name: string) => `${SUB_OUT}::${name}`;

  /** 改一个自定义项的名字：值跟着那一行走（rename 不是"新建一行"） */
  const renameCustom = (i: number, name: string) => {
    const old = custom[i];
    setCustom((list) => list.map((n, j) => (j === i ? name : n)));
    if (old === name) return;
    setValues((v) => {
      const next = { ...v, [customKey(name)]: v[customKey(old)] ?? "" };
      delete next[customKey(old)];
      return next;
    });
  };

  const removeCustom = (i: number) => {
    const old = custom[i];
    setCustom((list) => list.filter((_, j) => j !== i));
    setValues((v) => {
      const next = { ...v };
      delete next[customKey(old)];
      return next;
    });
  };

  const addCustom = () => {
    setCustom((list) => [...list, nextCustomOutName(list)]);
  };

  const rows = (list: { macro: string; label: string; value: number; role: string }[]) =>
    list.length ? (
      <ul className="buff-list" data-testid="buff-list">
        {list.map((r, i) => (
          <li key={`${r.macro}-${r.role}-${i}`}>
            <b>{r.label}</b>
            <span className="buff-val">{r.value}</span>
            <span className="dim">{r.role}</span>
          </li>
        ))}
      </ul>
    ) : (
      <p className="modal-hint" data-testid="buff-empty">
        （无）
      </p>
    );

  return (
    <div className="modal-mask" onMouseDown={onClose}>
      <div
        className="modal modal-role-panel"
        role="dialog"
        aria-label="角色面板"
        data-testid="role-panel-dialog"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2>角色面板 · {title}</h2>
        {/* 用户要求：删掉弹窗里的全部提示性文字（说明都搬到 F1 教程里） */}
        <div className="panel-macro-grid">
          <div className="panel-macro-head">
            <span className="pm-key">宏</span>
            <span className="pm-label">属性</span>
            <span>值（可写算式/变量）</span>
            <span className="pm-feed">喂给哪张卡</span>
            <span className="pm-show-head" title="勾选后显示在画布的角色面板上">显示</span>
          </div>
          {macros.map((m) => (
            <label className="panel-macro-row" key={m.key}>
              <span className="pm-key">{m.key}</span>
              <span className="pm-label">{m.label}</span>
              <input
                value={values[m.key] ?? ""}
                data-testid={`panel-${m.key}`}
                placeholder="留空 = 不启用"
                onChange={(e) => setValues((v) => ({ ...v, [m.key]: e.target.value }))}
              />
              <span className="pm-feed" title={m.feed}>
                {m.feed}
              </span>
              <input
                type="checkbox"
                className="pm-show"
                data-testid={`panel-show-${m.key}`}
                title="在画布的角色面板上显示这一项"
                checked={show.includes(m.key)}
                onChange={(e) =>
                  setShow((s) =>
                    e.target.checked ? [...s, m.key] : s.filter((k) => k !== m.key),
                  )
                }
              />
            </label>
          ))}
          {custom.length ? (
            <div className="panel-custom-block">
              <div className="panel-custom-title">
                自定义对外项（`{SUB_OUT}::名字`）—— 本角色没有这个属性，只把这份拐力给出去
              </div>
              {custom.map((name, i) => {
                const bad = !validCustomOut(name, customPattern);
                const dup = custom.filter((n) => n === name).length > 1;
                const clash = macros.some((m) => m.key === name);
                const err = bad
                  ? "名字只能用小写字母/数字/下划线，且要以字母开头"
                  : clash
                    ? "这个名字是固定面板宏，直接在上面那一行填值即可"
                    : dup
                      ? "名字重复了"
                      : "";
                return (
                  <div className="panel-macro-row panel-custom-row" key={`custom-${i}`}>
                    <span className="pm-key">
                      {SUB_OUT}::
                      <input
                        className="pm-custom-name"
                        value={name}
                        data-testid={`panel-custom-name-${i}`}
                        placeholder="buff"
                        onChange={(e) => renameCustom(i, e.target.value.trim())}
                      />
                    </span>
                    <span className="pm-label" />
                    <input
                      value={values[customKey(name)] ?? ""}
                      data-testid={`panel-custom-value-${i}`}
                      placeholder="留空 = 不给出去"
                      onChange={(e) =>
                        setValues((v) => ({ ...v, [customKey(name)]: e.target.value }))
                      }
                    />
                    <span className={err ? "pm-feed modal-warn" : "pm-feed"} data-testid={`panel-custom-hint-${i}`}>
                      {err || "拐力箭头 → 对面 in::名字"}
                    </span>
                    <button
                      type="button"
                      className="pm-custom-del"
                      title="删掉这一行"
                      data-testid={`panel-custom-del-${i}`}
                      onClick={() => removeCustom(i)}
                    >
                      ✕
                    </button>
                  </div>
                );
              })}
            </div>
          ) : null}
          <div className="panel-custom-add">
            <button type="button" data-testid="panel-custom-add" onClick={addCustom}>
              ＋ 添加自定义对外项
            </button>
          </div>
        </div>
        <div className="buff-stats">
          <div>
            <h3>给出去的拐（OUT）</h3>
            {rows(stats?.out ?? [])}
          </div>
          <div>
            <h3>收到的拐（IN）</h3>
            {rows(stats?.in ?? [])}
          </div>
        </div>
        <div className="modal-actions">
          <span className="grow" />
          <button type="button" onClick={onClose}>
            取消
          </button>
          <button type="button" className="primary" onClick={() => onSave(values, show, custom)}>
            确定
          </button>
        </div>
      </div>
    </div>
  );
}

export interface RoleNameDialogProps {
  initialName: string;
  /** 名字能不能用（重名 / 格式非法）；返回错误文案，空串 = 可以 */
  check?: (name: string) => string;
  /** 「角色」还是「武器」：只影响标题与输入框的标签（两者是同一套命名空间） */
  kind?: "角色" | "武器";
  onSave: (name: string) => void;
  onClose: () => void;
}

/**
 * 设置角色 / 武器名（右键标记的标题栏打开）。
 * 名字原来放在卡面上的单行输入框里，用户要求改成右键设置 —— 卡面省下这一行，
 * 也就能把卡片收窄。
 *
 * 名字必须唯一（用户要求：不许同名角色）：重名时当场红字提示并禁用「确定」，
 * 否则两个同名区域会互相干扰（变量前缀、拐力箭头、一键隐藏都按名字找）。
 */
export function RoleNameDialog({
  initialName,
  check,
  kind = "角色",
  onSave,
  onClose,
}: RoleNameDialogProps) {
  const [name, setName] = useState(initialName);
  const error = check ? check(name.trim()) : "";
  const canSave = !error;
  const title = `设置${kind}名`;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-mask" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-label={title}
        data-testid="role-name-dialog"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2>{title}</h2>
        <label className="modal-row">
          <span>{kind}名</span>
          <input
            value={name}
            data-testid="role-name-input"
            autoFocus
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && canSave) onSave(name.trim());
            }}
          />
        </label>
        {error ? (
          <p className="modal-hint modal-warn" data-testid="role-name-error">
            {error}
          </p>
        ) : null}
        <div className="modal-actions">
          <span className="grow" />
          <button type="button" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="primary"
            disabled={!canSave}
            onClick={() => onSave(name.trim())}
          >
            确定
          </button>
        </div>
      </div>
    </div>
  );
}

export interface NewProjectDialogProps {
  /** 当前工程名（预填，方便"另存为新项目"式的改名） */
  initialName: string;
  /** 当前画布上有几张卡片（说明文字已删，保留这个字段供调用方按需使用） */
  cardCount: number;
  onCreate: (name: string) => void;
  onClose: () => void;
}

/**
 * 新建项目：**先问工程名，再完整重置**（画布 / 工程名 / 撤销历史 / 浏览器本地存档）。
 * 这是工具栏唯一的重置入口（原来的「清空画布」已并进来）。
 *
 * 弹窗里只留「输入框 + 按钮」：那句"会清空画布…"的说明按用户要求一起删了。
 */
export function NewProjectDialog({
  initialName,
  onCreate,
  onClose,
}: NewProjectDialogProps) {
  const [name, setName] = useState(initialName);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-mask" onMouseDown={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-label="新建项目"
        data-testid="new-project-dialog"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2>新建项目</h2>
        <label className="modal-row">
          <span>工程名</span>
          <input
            value={name}
            data-testid="new-project-name"
            autoFocus
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onCreate(name.trim());
            }}
          />
        </label>
        <div className="modal-actions">
          <span className="grow" />
          <button type="button" onClick={onClose}>
            取消
          </button>
          <button type="button" className="primary" onClick={() => onCreate(name.trim())}>
            新建
          </button>
        </div>
      </div>
    </div>
  );
}

export interface HelpDialogProps {
  text: string;
  sections: string[];
  onClose: () => void;
}

export function HelpDialog({ text, sections, onClose }: HelpDialogProps) {
  const preRef = useRef<HTMLPreElement | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" || e.key === "F1") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  /**
   * 点章节名跳到那一节。
   *
   * 教程是一整块 `<pre>`（`pre-wrap` 会换行，按行数折算位置不准），所以用一个
   * 1 字符的 Range 量出那一节的**可视位置**，再把滚动条挪过去 —— 换行、缩放都不影响。
   */
  const jumpTo = (title: string) => {
    const pre = preRef.current;
    const node = pre?.firstChild;
    if (!pre || !node) return;
    const at = text.indexOf(`【${title}】`);
    if (at < 0) return;
    try {
      const range = document.createRange();
      range.setStart(node, at);
      range.setEnd(node, Math.min(at + 1, node.textContent?.length ?? at + 1));
      const target = range.getBoundingClientRect().top - pre.getBoundingClientRect().top;
      // 现位置 + 目标相对位置就是该滚到的 scrollTop（Range 与 pre 用同一坐标系）
      pre.scrollTop = Math.max(0, pre.scrollTop + target - 4);
    } catch {
      /* 量不出来就算了：不影响阅读 */
    }
  };

  return (
    <div className="modal-mask" onMouseDown={onClose}>
      <div
        className="modal modal-help"
        role="dialog"
        aria-label="使用教程"
        data-testid="help-dialog"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2>使用教程 (F1)</h2>
        {/* 章节导航：点一下跳到那一节（教程很长，没有导航很难读） */}
        <div className="help-nav">
          {sections.map((s) => (
            <button
              type="button"
              className="help-chip"
              key={s}
              data-testid={`help-nav-${s}`}
              title={`跳到「${s}」`}
              onClick={() => jumpTo(s)}
            >
              {s}
            </button>
          ))}
        </div>
        <pre className="help-text" ref={preRef}>
          {text}
        </pre>
        <div className="modal-actions">
          <span className="grow" />
          <button type="button" className="primary" onClick={onClose}>
            关闭 (Esc)
          </button>
        </div>
      </div>
    </div>
  );
}
