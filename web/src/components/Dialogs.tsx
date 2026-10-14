/**
 * 弹窗：设置结果变量（★结果卡片右键）、F1 教程。
 */
import { useEffect, useState } from "react";

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
        <p className="modal-hint">
          把结果的三元组分别命名为变量，供所有输入框 / 计算卡 / 变量卡片引用；
          留空表示不定义。同名时以结果卡片为准。
        </p>
        {labels.map((f) => (
          <label className="modal-row" key={f.key}>
            <span>{f.label}</span>
            <input
              value={values[f.key] ?? ""}
              data-testid={`var-${f.key}`}
              placeholder="例如 期望伤害"
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
  /** 卡片类型标题，仅用于提示文案 */
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
 */
export function NameCardDialog({
  initial,
  title,
  role,
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
        <p className="modal-hint">
          给「{title}」起个名字（例如「雷神增伤」），名字显示在标题栏。
          之后可以在任何输入框里引用这张卡的输出：<b>名字</b> 就是它的期望值，
          <b> 名字::暴击 </b> / <b> 名字::未暴击 </b> 取另外两个分量。
          {role ? ` 这张卡属于角色「${role}」。` : ""}
          留空并确定 = 取消命名。
        </p>
        <label className="modal-row">
          <span>卡片名</span>
          <input
            value={value}
            data-testid="card-name-input"
            placeholder="例如 雷神增伤"
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
  /** 当前面板值 {宏: 值文本} */
  initial: Record<string, string>;
  /** 拐力统计（OUT：给出去多少；IN：收进来多少） */
  stats?: { out: { macro: string; label: string; value: number; role: string }[];
            in: { macro: string; label: string; value: number; role: string }[] };
  onSave: (values: Record<string, string>) => void;
  onClose: () => void;
}

/**
 * 角色面板（右键角色标签打开）：上面是**可编辑的宏表**，下面是**拐力统计**。
 *
 * 「面板」是原神黑话里的角色属性表：面板项就是本角色命名空间里的变量，
 * 卡片字段留空时会用它们兜底；拖拐力箭头时也是把这张表加到目标角色的同名项上。
 */
export function RolePanelDialog({
  title,
  macros,
  initial,
  stats,
  onSave,
  onClose,
}: RolePanelDialogProps) {
  const [values, setValues] = useState<Record<string, string>>({ ...initial });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

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
        {macros.length === 0 ? (
          <p className="modal-hint modal-warn" data-testid="panel-macros-missing">
            后端没有返回面板宏词表（panelMacros）—— 服务很可能是旧进程。
            请双击 launcher.bat → [2] 停止 → [1] 启动，再刷新本页。
          </p>
        ) : null}
        <p className="modal-hint">
          面板项就是本角色命名空间里的变量（<code>{title}::atk</code> 这样引用）。
          卡片字段留空时会用这里的值兜底；拖拐力箭头时，本表会加到目标角色的同名项上。
          值可以写算式或引用其它变量。
        </p>
        <p className="modal-hint">
          同一个面板项有四个名字：<code>{title}::atk</code> 生效值（自身+收进来的拐）、
          <code>::own::atk</code> 纯自身、<code>::out::atk</code> 给出去的（=自身）、
          <code>::in::atk</code> 收进来的拐（多来源相加）。在角色内可省略角色名。
        </p>
        <div className="panel-macro-grid">
          {macros.map((m) => (
            <label className="panel-macro-row" key={m.key} title={m.feed}>
              <span className="pm-key">{m.key}</span>
              <span className="pm-label">{m.label}</span>
              <input
                value={values[m.key] ?? ""}
                data-testid={`panel-${m.key}`}
                placeholder="留空 = 不启用"
                onChange={(e) => setValues((v) => ({ ...v, [m.key]: e.target.value }))}
              />
            </label>
          ))}
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
          <button type="button" className="primary" onClick={() => onSave(values)}>
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
  /** 当前画布上有几张卡片（用来提示会被清空） */
  cardCount: number;
  onCreate: (name: string) => void;
  onClose: () => void;
}

/**
 * 新建项目：**先问工程名，再完整重置**（画布 / 工程名 / 撤销历史 / 浏览器本地存档）。
 * 这是工具栏唯一的重置入口（原来的「清空画布」已并进来）。
 */
export function NewProjectDialog({
  initialName,
  cardCount,
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
        <p className="modal-hint">
          会清空当前画布并重置工程名、撤销历史与浏览器里的本地自动存档（文件不会被动到）。
          {cardCount > 0 ? ` 当前画布上有 ${cardCount} 张卡片。` : ""}
        </p>
        <label className="modal-row">
          <span>工程名</span>
          <input
            value={name}
            data-testid="new-project-name"
            placeholder="例如 雷神直伤"
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
        <div className="help-nav">
          {sections.map((s) => (
            <span className="help-chip" key={s}>
              {s}
            </span>
          ))}
        </div>
        <pre className="help-text">{text}</pre>
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
