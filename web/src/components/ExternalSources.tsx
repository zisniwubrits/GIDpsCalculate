/**
 * 「外部域」卡片的来源列表：一行一个单行输入框。
 *
 * 交互（用户要求）：
 *   * 回车 → 在**下面**加一行空输入框，光标跟过去；
 *   * 空行按退格 → 把这一行删掉，光标回到上一行；
 *   * 永远至少留一个输入框（删光了卡片就没地方填了）。
 *
 * 补全（用户要求）：目录名 / 文件名 / 域名由后端给候选（`/api/external/suggest`）。
 * **不用 datalist** —— 候选是异步到的，浏览器不会刷新已经弹出的原生下拉，
 * 实测"打了 :: 什么都不出来"。这里自己画一行候选，点一下就填进去。
 *
 * 存的是**一个多行字符串**（`ext_sources`），后端按行解析；
 * 这里只负责把字符串拆成输入框再拼回去（纯函数在 model.ts，好单测）。
 */
import { useEffect, useRef, useState } from "react";
import { suggestExternal } from "../api";
import {
  insertSourceLine,
  removeSourceLine,
  setSourceLine,
  sourceLines,
} from "../model";

export interface ExternalSourcesProps {
  value: unknown;
  onChange: (next: string) => void;
  /** 测试与定位用（卡片 id） */
  id: string;
  disabled?: boolean;
  /** 相对路径的基准目录（当前工程目录）；不传就由后端用记住的目录 */
  baseDir?: string;
}

type HintMode = "path" | "domain";

interface Hints {
  mode: HintMode;
  list: string[];
}

export default function ExternalSources({
  value,
  onChange,
  id,
  disabled,
  baseDir,
}: ExternalSourcesProps) {
  const lines = sourceLines(value);
  const inputs = useRef<Array<HTMLInputElement | null>>([]);
  /** 下次渲染后要把光标放到哪一行（插入 / 删除之后）；用完必须清掉 */
  const [focusAt, setFocusAt] = useState<number | null>(null);
  /** 当前在编辑哪一行（决定候选列表给谁看） */
  const [active, setActive] = useState<number | null>(null);
  const [hints, setHints] = useState<Hints | null>(null);

  // 聚焦只做一次：以前写在 ref 回调里、且 focusAt 用完不清，于是每次重渲染都会把
  // 光标抢回那一行 —— 表现就是"在别的行打字，光标跳到那一行末尾"。
  // 现在只搬一次，而且**等新加的那一行渲染出来**再搬（元素还没到时留着，下次再来）。
  useEffect(() => {
    if (focusAt === null) return;
    const el = inputs.current[focusAt];
    if (!el) return;
    el.focus();
    const end = el.value.length;
    el.setSelectionRange(end, end);
    setFocusAt(null);
  }, [focusAt, lines.length]);

  /** 拉候选：光标在 `::` 后面补域名，否则补路径 */
  const timer = useRef<number | null>(null);
  const seq = useRef(0);
  const askHints = (text: string, caret: number | null | undefined) => {
    const sep = text.indexOf("::");
    const at = caret ?? text.length;
    const mode: HintMode = sep >= 0 && at > sep + 1 ? "domain" : "path";
    // 只认**最后一次**请求的结果：否则上一拍的响应晚到，会把新的候选覆盖掉
    //（表现为"打了 :: 却列出一堆文件名"）
    const mine = ++seq.current;
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      void suggestExternal(text, baseDir)
        .then((res) => {
          if (mine !== seq.current) return;         // 过时的响应直接丢
          const list = (mode === "domain" ? res.domains : res.paths).slice(0, 20);
          setHints(list.length ? { mode, list } : null);
        })
        .catch(() => {
          if (mine === seq.current) setHints(null);
        });
    }, 120);
  };

  /** 点候选：路径换掉 `::` 之前那段，域名换掉之后那段 */
  const apply = (index: number, pick: string, mode: HintMode) => {
    const line = sourceLines(value)[index] ?? "";
    const sep = line.indexOf("::");
    const next =
      mode === "domain"
        ? (sep >= 0 ? line.slice(0, sep + 2) : line + "::") + pick
        : pick + (sep >= 0 ? line.slice(sep) : "");
    onChange(setSourceLine(value, index, next));
    setActive(index);
    askHints(next, next.length);
  };

  const onKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    // 中文输入法里回车是"确认候选词"，别当成加行
    if (e.nativeEvent.isComposing) return;
    if (e.key === "Escape") {
      setHints(null);
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      onChange(insertSourceLine(value, index));
      setFocusAt(index + 1);
      setHints(null);
      return;
    }
    if (e.key === "Backspace" && lines[index] === "" && lines.length > 1) {
      // 只删空行；非空行让浏览器正常退格（否则删字都变删行）
      e.preventDefault();
      onChange(removeSourceLine(value, index));
      setFocusAt(Math.max(0, index - 1));
      setHints(null);
    }
  };

  return (
    <div className="ext-sources" data-testid={`ext-sources-${id}`}>
      {lines.map((line, index) => (
        <span className="ext-source-line" key={index}>
          <input
            ref={(el) => {
              inputs.current[index] = el;
            }}
            className="ext-source-row"
            data-testid={`ext-source-${id}-${index}`}
            value={line}
            disabled={disabled}
            spellCheck={false}
            onChange={(e) => {
              const caret = e.target.selectionStart;
              onChange(setSourceLine(value, index, e.target.value));
              setActive(index);
              askHints(e.target.value, caret);
            }}
            onFocus={(e) => {
              setActive(index);
              askHints(e.currentTarget.value, e.currentTarget.selectionStart);
            }}
            onBlur={() => {
              // 焦点离开就把候选收起来（用户要求）；点候选按钮不会走到这里 ——
              // 候选条的 mousedown 已经 preventDefault，输入框不会失焦
              setHints(null);
              setActive(null);
            }}
            onKeyDown={(e) => onKeyDown(index, e)}
          />
          {active === index && hints ? (
            <span
              className="ext-hints"
              data-testid={`ext-hints-${id}-${index}`}
              // 用 mousedown 抢在输入框失焦之前填进去
              onMouseDown={(e) => {
                e.preventDefault();
                e.stopPropagation();
              }}
            >
              {hints.list.map((pick) => (
                <button
                  type="button"
                  className="ext-hint"
                  key={pick}
                  data-testid={`ext-hint-${id}-${index}-${pick}`}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    apply(index, pick, hints.mode);
                  }}
                >
                  {pick}
                </button>
              ))}
            </span>
          ) : null}
        </span>
      ))}
    </div>
  );
}
