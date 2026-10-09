/**
 * 连线：正交走线 + 圆角拐弯 + 箭头（与旧版 tkinter 画法一致）。
 *
 * 选中连线后，中点会出现一个小 ✕ 直接删除；也可以用 Delete 键。
 */
import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  type Edge,
  type EdgeProps,
} from "@xyflow/react";
import { memo } from "react";

export interface LinkEdgeData extends Record<string, unknown> {
  src: string;
  dst: string;
  port: number;
  /** 悬停某张卡片时，与它无关的连线变淡 */
  dim?: boolean;
  onDelete: (id: string) => void;
}

export type CardRFEdge = Edge<LinkEdgeData, "card">;

function CardEdgeView({
  id,
  data,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  selected,
}: EdgeProps<CardRFEdge>) {
  const [path, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    borderRadius: 12,
  });

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        className={`card-edge${selected ? " card-edge-sel" : ""}${data?.dim ? " card-edge-dim" : ""}`}
      />
      {selected ? (
        <EdgeLabelRenderer>
          <button
            type="button"
            className="edge-del"
            title="删除这条连线"
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
            onClick={() => data?.onDelete(id)}
          >
            ✕
          </button>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

export default memo(CardEdgeView);
