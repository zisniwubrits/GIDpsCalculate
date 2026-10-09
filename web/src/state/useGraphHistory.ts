/**
 * 画布状态 + 撤销/重做。
 *
 * 与旧版 tkinter 一致：编辑停顿 450ms 后自动记录一步，连续输入不会产生一堆历史。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { CardNode, GraphLinkJSON } from "../types";

export interface GraphState {
  nodes: CardNode[];
  links: GraphLinkJSON[];
}

export const HISTORY_MAX = 80;
export const HISTORY_DELAY = 450;

export interface History {
  state: GraphState;
  /** 更新画布并（防抖地）记录一步历史 */
  apply: (updater: (prev: GraphState) => GraphState) => void;
  /** 立即结算待记录的历史（例如按下撤销前） */
  flush: () => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
  /** 用新状态替换画布并清空历史（打开工程 / 清空画布） */
  reset: (next: GraphState) => boolean;
}

export function useGraphHistory(initial: GraphState): History {
  const [state, setState] = useState<GraphState>(initial);
  const past = useRef<GraphState[]>([]);
  const future = useRef<GraphState[]>([]);
  const pending = useRef<GraphState | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [, bump] = useState(0);
  const stateRef = useRef(state);
  stateRef.current = state;

  const settle = useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    if (pending.current !== null) {
      past.current.push(pending.current);
      if (past.current.length > HISTORY_MAX) past.current.shift();
      future.current = [];
      pending.current = null;
      bump((v) => v + 1);
    }
  }, []);

  const apply = useCallback(
    (updater: (prev: GraphState) => GraphState) => {
      const prev = stateRef.current;
      const next = updater(prev);
      if (next === prev) return;
      if (pending.current === null) pending.current = prev;
      stateRef.current = next;
      setState(next);
      if (timer.current !== null) clearTimeout(timer.current);
      timer.current = setTimeout(settle, HISTORY_DELAY);
    },
    [settle],
  );

  const flush = useCallback(() => settle(), [settle]);

  const undo = useCallback(() => {
    settle();
    const prev = past.current.pop();
    if (!prev) return;
    future.current.push(stateRef.current);
    stateRef.current = prev;
    setState(prev);
    bump((v) => v + 1);
  }, [settle]);

  const redo = useCallback(() => {
    settle();
    const next = future.current.pop();
    if (!next) return;
    past.current.push(stateRef.current);
    stateRef.current = next;
    setState(next);
    bump((v) => v + 1);
  }, [settle]);

  const reset = useCallback((next: GraphState) => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    pending.current = null;
    past.current = [];
    future.current = [];
    stateRef.current = next;
    setState(next);
    bump((v) => v + 1);
    return true;
  }, []);

  useEffect(() => () => {
    if (timer.current !== null) clearTimeout(timer.current);
  }, []);

  return {
    state,
    apply,
    flush,
    undo,
    redo,
    canUndo: past.current.length > 0 || pending.current !== null,
    canRedo: future.current.length > 0,
    reset,
  };
}
