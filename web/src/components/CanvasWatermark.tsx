/**
 * 画布水印：把工程名斜着平铺在画布平面上（最底层，跟随平移与缩放）。
 *
 * 两个关键实现点（都是查过 React Flow 自带 CSS / DOM 结构后定的）：
 *
 * 1. **跟随平移缩放**：`<ReactFlow>` 的 children 落在 `.react-flow` 根里、
 *    **不在** `.react-flow__viewport` 内部，所以拿不到现成的 transform。
 *    这里用 `useViewport()` 取当前视口，按 React Flow 自己的做法渲染一个铺满容器的
 *    SVG `<pattern>`：`patternTransform = translate(x,y) scale(zoom) rotate(-24)`，
 *    平铺间隔与字号都写在**画布单位**里 —— 于是水印与卡片同步平移、缩放。
 *
 * 2. **最底层**：React Flow 的层级是 点阵背景 -1 / pane 1 / viewport 2，
 *    所以给水印 `z-index: -2`（见 styles.css），比点阵还低，卡片永远压在它上面；
 *    `pointer-events: none` 保证不影响画布拖动、框选与连线。
 */

import { useId } from "react";
import { useViewport } from "@xyflow/react";

/** 工程名为空时水印显示的字样（用户确认过） */
export const WATERMARK_FALLBACK = "未命名";

/** 平铺间隔与字号都用画布单位（随缩放一起放大缩小） */
const TILE_W = 560;
const TILE_H = 360;
const FONT = 14;
/** 倾斜角度：斜放的水印观感 */
const TILT = -24;

export default function CanvasWatermark({ name }: { name: string }) {
  const { x, y, zoom } = useViewport();
  const label = name.trim() || WATERMARK_FALLBACK;
  // useId 里带冒号，放进 url(#…) 需要去掉
  const patternId = `wm-${useId().replace(/:/g, "")}`;

  return (
    <svg
      className="canvas-watermark"
      data-testid="canvas-watermark"
      data-label={label}
      aria-hidden="true"
    >
      <defs>
        <pattern
          id={patternId}
          patternUnits="userSpaceOnUse"
          width={TILE_W}
          height={TILE_H}
          patternTransform={`translate(${x},${y}) scale(${zoom}) rotate(${TILT})`}
        >
          <text className="wm-text" x="12" y={FONT + 6} fontSize={FONT}>
            {label}
          </text>
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#${patternId})`} />
    </svg>
  );
}
