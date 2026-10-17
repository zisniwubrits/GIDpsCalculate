/**
 * 带关键字高亮的文本框（透明 textarea 叠在带颜色的 pre 上）。
 *
 * 为什么这么做：`<textarea>` 里的文字没法单独上色，只能在下层画一份带
 * `<span>` 的副本，textarea 自身背景透明、只留光标和选区。
 * 滚动位置、字体、内边距、换行规则必须和 textarea 完全一致，否则会错位。
 *
 * 用途：「变量」卡片的定义区（own/out/in 与 atk 这类宏名深蓝高亮）。
 */
import { useLayoutEffect, useRef } from "react";
import { highlightTokens } from "../model";

export interface CodeFieldProps {
  value: unknown;
  onChange: (next: string) => void;
  /** 要额外高亮的词（面板宏名，来自 schema） */
  macros?: readonly string[];
  className?: string;
  rows?: number;
  testId?: string;
  disabled?: boolean;
}

export default function CodeField({
  value,
  onChange,
  macros = [],
  className = "",
  rows,
  testId,
  disabled,
}: CodeFieldProps) {
  const text = String(value ?? "");
  const area = useRef<HTMLTextAreaElement | null>(null);
  const layer = useRef<HTMLPreElement | null>(null);
  const tokens = highlightTokens(text, macros);

  // textarea 滚了，下层的副本要跟着滚，否则高亮会错位
  useLayoutEffect(() => {
    const a = area.current;
    const p = layer.current;
    if (!a || !p) return;
    p.scrollTop = a.scrollTop;
    p.scrollLeft = a.scrollLeft;
  });

  return (
    <div className={`code-wrap${className ? " " + className : ""}`}>
      <pre className="code-hl" ref={layer} aria-hidden="true">
        {tokens.map((t, i) => (
          <span className={t.kind === "plain" ? undefined : `tok-${t.kind}`} key={i}>
            {t.text}
          </span>
        ))}
        {/* 末尾换行时 textarea 会多一行，副本补一行保证高度一致 */}
        {"\n"}
      </pre>
      <textarea
        ref={area}
        className="f-input f-area f-bare code-input"
        data-testid={testId}
        value={text}
        rows={rows}
        spellCheck={false}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onScroll={(e) => {
          const p = layer.current;
          if (!p) return;
          p.scrollTop = e.currentTarget.scrollTop;
          p.scrollLeft = e.currentTarget.scrollLeft;
        }}
      />
    </div>
  );
}
