/**
 * Vitest 全局设置：补上 jsdom 缺失、但 React Flow 需要的浏览器 API。
 */
import "@testing-library/jest-dom/vitest";

/** jsdom 没有 ResizeObserver：观察时立刻回调一次，让 React Flow 量到尺寸。 */
class ResizeObserverStub {
  private readonly callback: ResizeObserverCallback;

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }

  observe(target: Element): void {
    const width = sizeOf(target, "w");
    const height = sizeOf(target, "h");
    const entry = {
      target,
      contentRect: { x: 0, y: 0, top: 0, left: 0, right: width, bottom: height, width, height },
      borderBoxSize: [{ inlineSize: width, blockSize: height }],
      contentBoxSize: [{ inlineSize: width, blockSize: height }],
      devicePixelContentBoxSize: [{ inlineSize: width, blockSize: height }],
    } as unknown as ResizeObserverEntry;
    this.callback([entry], this as unknown as ResizeObserver);
  }

  unobserve(): void {}

  disconnect(): void {}
}

if (!("ResizeObserver" in globalThis)) {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
}

if (!("DOMMatrixReadOnly" in globalThis)) {
  class DOMMatrixStub {
    m22 = 1;
    constructor(_t?: string) {}
  }
  (globalThis as unknown as { DOMMatrixReadOnly: unknown }).DOMMatrixReadOnly = DOMMatrixStub;
}

if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

// 剪贴板：jsdom 里 isSecureContext 为 false，会让 copyText 走 execCommand 兜底
Object.defineProperty(window, "isSecureContext", { value: true, configurable: true });
if (typeof document.execCommand !== "function") {
  document.execCommand = (() => true) as typeof document.execCommand;
}

// React Flow 依赖 offsetWidth/offsetHeight 判断节点是否有尺寸（jsdom 恒为 0，
// 会让节点被标记 visibility:hidden，从而被 RTL 视为不可访问）。
const sizeOf = (el: Element, axis: "w" | "h"): number => {
  if (el.classList?.contains("react-flow__node")) return axis === "w" ? 320 : 200;
  if (el.classList?.contains("react-flow") || el.closest?.(".react-flow")) {
    return axis === "w" ? 1280 : 800;
  }
  return 0;
};

for (const prop of ["offsetWidth", "offsetHeight", "clientWidth", "clientHeight"] as const) {
  const axis = prop.includes("Width") ? "w" : "h";
  Object.defineProperty(HTMLElement.prototype, prop, {
    configurable: true,
    get(this: HTMLElement) {
      return sizeOf(this, axis);
    },
  });
}

// d3-drag 在 jsdom 下会因合成事件的 event.view 为 null 抛未捕获异常；
// 已在 vite.config.ts 里把它在测试环境替换成空实现（见 src/test/d3-drag-stub.ts）。

const originalRect = Element.prototype.getBoundingClientRect;
Element.prototype.getBoundingClientRect = function (this: Element) {
  if (this.classList?.contains("react-flow")) {
    return {
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: 1280,
      bottom: 800,
      width: 1280,
      height: 800,
      toJSON: () => ({ width: 1280, height: 800 }),
    } as DOMRect;
  }
  return originalRect.call(this);
};
