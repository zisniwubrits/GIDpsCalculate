/**
 * 测试环境下的 d3-drag 空实现（通过 vite.config.ts 的 resolve.alias 替换）。
 *
 * 原因：d3-drag 的 `nodrag(event.view)` 在 jsdom 里会拿到 null（合成事件没有 view），
 * 于是抛未捕获异常。jsdom 也没有真实布局，节点拖拽本来就无法在测试里验证，
 * 因此这里给一个「链式调用 + 可被 selection.call() 调用」的空壳。
 *
 * 生产构建**不会**走这个替换（alias 只在 VITEST 环境生效）。
 */
type Chain = Record<string, unknown> & { (...args: unknown[]): unknown };

const target = ((selection?: unknown) => selection ?? target) as Chain;

const stub = new Proxy(target, {
  get(obj, prop) {
    if (prop === "then") return undefined; // 避免被当作 thenable
    if (!(prop in obj)) {
      Object.defineProperty(obj, prop, {
        value: () => stub,
        configurable: true,
      });
    }
    return obj[prop as string];
  },
}) as unknown as Chain;

export function drag(): Chain {
  return stub;
}

export default { drag };
