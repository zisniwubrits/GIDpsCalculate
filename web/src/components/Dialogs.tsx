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
