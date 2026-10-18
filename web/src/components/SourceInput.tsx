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
  const abort = useRef<AbortController | null>(null);
  /**
   * 候选缓存：**同一个目录只向后端要一次**，之后在本地过滤前缀。
   * 补全卡顿的根源不是补全本身（后端一次 0.2ms），而是打字会连带触发整表重算，
   * 请求排在重算后面 —— 少发请求、发出去能取消，手感就顺了。
   */
  const dirCache = useRef(new Map<string, { paths: string[]; domains: string[] }>());

  /** 拆出「目录部分 + 前缀」：``data/米`` → ``("data/", "米")`` */
  const splitPath = (text: string): [string, string] => {
    const cut = Math.max(text.lastIndexOf("/"), text.lastIndexOf("\\"));
    return cut < 0 ? ["", text] : [text.slice(0, cut + 1), text.slice(cut + 1)];
  };

  /** 拉候选：光标在 `::` 后面补域名，否则补路径（带本地缓存 + 本地过滤） */
  const ask = (text: string, caret: number | null | undefined) => {
    const sep = text.indexOf("::");
    const at = caret ?? text.length;
    const mode: HintMode = sep >= 0 && at > sep + 1 ? "domain" : "path";
    // 请求只要"目录" / "文件"这半截，前缀在本地筛 —— 同一个目录只请求一次
    const key = mode === "domain" ? text.slice(0, sep) : splitPath(text)[0];
    const typed = mode === "domain" ? text.slice(sep + 2) : splitPath(text)[1];
    const mine = ++seq.current;                    // 只认最后一次请求
    if (timer.current !== null) window.clearTimeout(timer.current);

    /** 把候选按已输入的前缀筛一遍（大小写不敏感），最多 20 条 */
    const pick = (paths: string[], domains: string[]) => {
      if (mine !== seq.current) return;
      const low = typed.trim().toLowerCase();
      const list = (mode === "domain" ? domains : paths).filter(
        (item) => !low || displayName(item).toLowerCase().startsWith(low),
      );
      setHints(list.length ? { mode, list: list.slice(0, 20) } : null);
    };

    timer.current = window.setTimeout(() => {
      const cached = dirCache.current.get(key);
      if (cached) {
        pick(cached.paths, cached.domains);       // 同一目录：本地筛，不再发请求
        return;
      }
      abort.current?.abort();
      abort.current = new AbortController();
      const query = mode === "domain" ? key + "::" : key;
      void suggestExternal(query, baseDir, abort.current.signal)
        .then((res) => {
          dirCache.current.set(key, { paths: res.paths, domains: res.domains });
          pick(res.paths, res.domains);
        })
        .catch(() => {
          if (mine === seq.current) setHints(null);
        });
    }, 200);
  };

  /** 候选里"名字"那段（目录要保留结尾的 /） */
  const displayName = (candidate: string) => {
    const [dir, name] = splitPath(candidate);
    return name || dir;
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
    // 选中一个**文件**（不是目录：目录候选带结尾的 /）时，自动补上 `::`
    // 并把光标放到后面 —— 这样域名的候选会立刻弹出来。文件里有多个域时
    // 不写 `::域` 是读不到拐力的（后端会提示"文件里有 N 个域"）。
    const pickFile = hints?.mode === "path" && !pick.endsWith("/");
    const next =
      hints?.mode === "domain"
        ? (sep >= 0 ? value.slice(0, sep + 2) : value + "::") + pick
        : pick + (sep >= 0 ? value.slice(sep) : pickFile ? "::" : "");
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
