/**
 * 带关键字高亮的单行输入框（透明 input 叠在带色的副本上）。
 *
 * 卡片里的数值 / 百分比 / 文本字段都支持写算式与变量（`atk*1.5`、`in::dmg`），
 * 所以这些地方也把 own / out / in 与面板宏名高亮出来（用户要求：抗性区等卡片
 * 里的关键字一起高亮）。
 *
 * 和 CodeField 一样：副本负责上色，input 只负责编辑（值是唯一真相）。
 * 单行不换行，所以副本用 `white-space: pre`，滚动位置同步一次即可。
 */
import { useLayoutEffect, useRef } from "react";
import { highlightTokens } from "../model";

export interface CodeInputProps {
  value: unknown;
  onChange: (next: string) => void;
  /** 要额外高亮的词（面板宏名，来自 schema） */
  macros?: readonly string[];
  className?: string;
  testId?: string;
  disabled?: boolean;
  title?: string;
}

export default function CodeInput({
  value,
  onChange,
  macros = [],
  className = "",
  testId,
  disabled,
  title,
}: CodeInputProps) {
  const text = String(value ?? "");
  const input = useRef<HTMLInputElement | null>(null);
  const layer = useRef<HTMLSpanElement | null>(null);
  const tokens = highlightTokens(text, macros);

  // input 横向滚动了，副本要跟着滚，否则高亮会错位
  useLayoutEffect(() => {
    const i = input.current;
    const p = layer.current;
    if (!i || !p) return;
    p.scrollLeft = i.scrollLeft;
  });

  return (
    <span className={`code-line${className ? " " + className : ""}`}>
      <span className="code-hl code-hl-line" ref={layer} aria-hidden="true">
        {tokens.map((t, i) => (
          <span className={t.kind === "plain" ? undefined : `tok-${t.kind}`} key={i}>
            {t.text}
          </span>
        ))}
      </span>
      <input
        ref={input}
        className="f-input code-input"
        data-testid={testId}
        value={text}
        spellCheck={false}
        disabled={disabled}
        title={title}
        onChange={(e) => onChange(e.target.value)}
        onScroll={(e) => {
          const p = layer.current;
          if (p) p.scrollLeft = e.currentTarget.scrollLeft;
        }}
      />
    </span>
  );
}
