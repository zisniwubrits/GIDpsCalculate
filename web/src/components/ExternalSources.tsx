/**
 * 「外部域」卡片的来源列表：一行一个单行输入框。
 *
 * 交互（用户要求）：
 *   * 回车 → 在**下面**加一行空输入框，光标跟过去；
 *   * 空行按退格 → 把这一行删掉，光标回到上一行；
 *   * 永远至少留一个输入框（删光了卡片就没地方填了）。
 *
 * 补全：交给 SourceInput（小弹窗，候选由后端 `/api/external/suggest` 给）。
 * 存的是**一个多行字符串**（`ext_sources`），后端按行解析；
 * 这里只负责把字符串拆成输入框再拼回去（纯函数在 model.ts，好单测）。
 */
import { useEffect, useRef, useState } from "react";
import {
  insertSourceLine,
  removeSourceLine,
  setSourceLine,
  sourceLines,
} from "../model";
import SourceInput from "./SourceInput";

export interface ExternalSourcesProps {
  value: unknown;
  onChange: (next: string) => void;
  /** 测试与定位用（卡片 id） */
  id: string;
  disabled?: boolean;
  /** 相对路径的基准目录（当前工程目录）；不传就由后端用记住的目录 */
  baseDir?: string;
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

  // 光标只搬一次，而且**等新加的那一行渲染出来**再搬（元素还没到时留着，下次再来）。
  useEffect(() => {
    if (focusAt === null) return;
    const el = inputs.current[focusAt];
    if (!el) return;
    el.focus();
    const end = el.value.length;
    el.setSelectionRange(end, end);
    setFocusAt(null);
  }, [focusAt, lines.length]);

  return (
    <div className="ext-sources" data-testid={`ext-sources-${id}`}>
      {lines.map((line, index) => (
        <span className="ext-source-line" key={index}>
          <SourceInput
            value={line}
            disabled={disabled}
            baseDir={baseDir}
            className="ext-source-row"
            testId={`ext-source-${id}-${index}`}
            inputRef={(el) => {
              inputs.current[index] = el;
            }}
            onChange={(next) => onChange(setSourceLine(value, index, next))}
            onEnter={() => {
              onChange(insertSourceLine(value, index));
              setFocusAt(index + 1);          // 光标跟到新加的那一行
            }}
            onEmptyBackspace={() => {
              if (lines.length <= 1) return;  // 只剩一条就不删
              onChange(removeSourceLine(value, index));
              setFocusAt(Math.max(0, index - 1));
            }}
          />
        </span>
      ))}
    </div>
  );
}
