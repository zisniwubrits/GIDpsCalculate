/**
 * 「来源」输入框：单行输入 + **小弹窗**自动补全。
 *
 * 为什么用小弹窗：补全候选原来是排在输入框下面的一行（`ext-hints`），
 * 会把卡片撑高、看起来像多出来一块；而且候选是异步到的，浏览器原生 datalist
 * 不会刷新已弹出的列表。这里改用挂到 body 的浮动小弹窗，按输入框位置定位。
 *
 * 补全内容由后端给（`/api/external/suggest`）：光标在 `::` 后面补域名，否则补路径
 * （目录 / 文件名）。回车加一条、空行退格删一条这类**增删逻辑留给调用方**，
 * 这里只透传 onEnter / onEmptyBackspace。
 */
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { suggestExternal } from "../api";

export interface SourceInputProps {
  value: string;
  onChange: (next: string) => void;
  /** 回车（调用方负责加一条并把光标搬过去） */
  onEnter?: () => void;
  /** 正在空行上按退格（调用方负责删掉这一条） */
  onEmptyBackspace?: () => void;
  disabled?: boolean;
  baseDir?: string;
  className?: string;
  testId?: string;
  placeholder?: string;
  /** 输入框的固有宽度（字符数）：长文件名时让列宽跟着内容走，别把路径截断 */
  size?: number;
  /** 调用方想自己管焦点时传进来（「外部域」插入一行后要把光标搬过去） */
  inputRef?: (el: HTMLInputElement | null) => void;
}

type HintMode = "path" | "domain";

export default function SourceInput({
  value,
  onChange,
  onEnter,
  onEmptyBackspace,
  disabled,
  baseDir,
  className = "",
  testId,
  placeholder,
  size,
  inputRef,
}: SourceInputProps) {
  const input = useRef<HTMLInputElement | null>(null);
  const [hints, setHints] = useState<{ mode: HintMode; list: string[] } | null>(null);
  const [pos, setPos] = useState<{ left: number; top: number; width: number } | null>(null);
  const seq = useRef(0);
  const timer = useRef<number | null>(null);

  /** 拉候选：光标在 `::` 后面补域名，否则补路径 */
  const ask = (text: string, caret: number | null | undefined) => {
    const sep = text.indexOf("::");
    const at = caret ?? text.length;
    const mode: HintMode = sep >= 0 && at > sep + 1 ? "domain" : "path";
    const mine = ++seq.current;                    // 只认最后一次请求
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      void suggestExternal(text, baseDir)
        .then((res) => {
          if (mine !== seq.current) return;
          const list = (mode === "domain" ? res.domains : res.paths).slice(0, 20);
          setHints(list.length ? { mode, list } : null);
        })
        .catch(() => {
          if (mine === seq.current) setHints(null);
        });
    }, 120);
  };

  /** 小弹窗跟着输入框走（挂到 body 上，不会被卡片裁掉） */
  useEffect(() => {
    if (!hints) {
      setPos(null);
      return;
    }
    const el = input.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setPos({ left: r.left, top: r.bottom + 2, width: Math.max(180, r.width) });
  }, [hints, value]);

  // 关掉弹窗：点别处 / 滚动画布 / 按 Esc
  useEffect(() => {
    if (!hints) return;
    const close = () => setHints(null);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [hints]);

  const apply = (pick: string) => {
    const sep = value.indexOf("::");
    const next =
      hints?.mode === "domain"
        ? (sep >= 0 ? value.slice(0, sep + 2) : value + "::") + pick
        : pick + (sep >= 0 ? value.slice(sep) : "");
    onChange(next);
    setHints(null);
    // 补完继续留在输入框里，光标放到末尾
    const el = input.current;
    if (el) {
      el.focus();
      window.setTimeout(() => el.setSelectionRange(next.length, next.length), 0);
    }
  };

  return (
    <>
      <input
        ref={(el) => {
          input.current = el;
          inputRef?.(el);
        }}
        className={`f-input${className ? " " + className : ""}`}
        data-testid={testId}
        value={value}
        size={size}
        title={value || undefined}
        disabled={disabled}
        spellCheck={false}
        placeholder={placeholder}
        onChange={(e) => {
          onChange(e.target.value);
          ask(e.target.value, e.target.selectionStart);
        }}
        onFocus={(e) => ask(e.currentTarget.value, e.currentTarget.selectionStart)}
        onBlur={() => setHints(null)}
        onKeyDown={(e) => {
          if (e.nativeEvent.isComposing) return;
          if (e.key === "Escape") {
            setHints(null);
            return;
          }
          if (e.key === "Enter") {
            e.preventDefault();
            setHints(null);
            onEnter?.();
            return;
          }
          if (e.key === "Backspace" && value === "") {
            e.preventDefault();
            setHints(null);
            onEmptyBackspace?.();
          }
        }}
      />
      {hints && pos
        ? createPortal(
            <div
              className="src-pop"
              data-testid={testId ? `${testId}-hints` : undefined}
              style={{ left: pos.left, top: pos.top, minWidth: pos.width }}
              // 用 mousedown 抢在输入框失焦之前填进去
              onMouseDown={(e) => {
                e.preventDefault();
                e.stopPropagation();
              }}
            >
              {hints.list.map((pick) => (
                <button
                  type="button"
                  className="src-pop-item"
                  key={pick}
                  data-testid={testId ? `${testId}-hint-${pick}` : undefined}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    apply(pick);
                  }}
                >
                  {pick}
                </button>
              ))}
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
