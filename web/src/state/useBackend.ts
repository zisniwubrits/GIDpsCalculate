/**
 * 与后端交互的 React 钩子：加载 schema / 教程，防抖求值整张图。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { evaluateGraph, fetchHelp, fetchSchema } from "../api";
import type { EvaluateResult, GraphJSON, Schema } from "../types";

export const EVAL_DEBOUNCE = 140;

export function useSchema(): { schema: Schema | null; error: string | null; reload: () => void } {
  const [schema, setSchema] = useState<Schema | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    fetchSchema(ctrl.signal)
      .then((s) => {
        setSchema(s);
        setError(null);
      })
      .catch((e: unknown) => {
        if ((e as Error)?.name === "AbortError") return;
        setError((e as Error).message);
      });
    return () => ctrl.abort();
  }, [nonce]);

  return { schema, error, reload: useCallback(() => setNonce((n) => n + 1), []) };
}

export function useHelp(): { text: string; sections: string[] } {
  const [help, setHelp] = useState<{ text: string; sections: string[] }>({
    text: "教程加载中…",
    sections: [],
  });
  useEffect(() => {
    const ctrl = new AbortController();
    fetchHelp(ctrl.signal)
      .then(setHelp)
      .catch(() => undefined);
    return () => ctrl.abort();
  }, []);
  return help;
}

export interface Evaluation {
  data: EvaluateResult | null;
  error: string | null;
  pending: boolean;
}

/** 把整张图交给后端求值（防抖 + 丢弃过期响应）。 */
export function useEvaluate(graph: GraphJSON, enabled = true): Evaluation {
  const serialized = useMemo(() => JSON.stringify(graph), [graph]);
  const [data, setData] = useState<EvaluateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const seq = useRef(0);

  useEffect(() => {
    if (!enabled) return undefined;
    const mine = seq.current + 1;
    seq.current = mine;
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      setPending(true);
      evaluateGraph(JSON.parse(serialized) as GraphJSON, ctrl.signal)
        .then((res) => {
          if (seq.current !== mine) return;
          setData(res);
          setError(null);
        })
        .catch((e: unknown) => {
          if ((e as Error)?.name === "AbortError" || seq.current !== mine) return;
          setError((e as Error).message);
        })
        .finally(() => {
          if (seq.current === mine) setPending(false);
        });
    }, EVAL_DEBOUNCE);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [serialized, enabled]);

  return { data, error, pending };
}
