/**
 * 角色 / 武器卡片的**拐力端口排布**（纯函数部分）。
 *
 * 为什么单测在这里：jsdom 没有布局，端口到底落在卡片哪个位置只能靠
 * 「算出来的 left 值」来验（样式表另有一份基准位置，见 styles.test.ts）。
 */
import { describe, expect, it } from "vitest";
import { buffPortCount, portOffset } from "./CardNode";

describe("拐力端口的排布", () => {
  it("入度默认给 3 个位置，接满了自动再给两个（想收几份拐都行）", () => {
    expect(buffPortCount(0, 3)).toBe(3);
    expect(buffPortCount(2, 3)).toBe(3);
    expect(buffPortCount(3, 3)).toBe(5);      // 3 个都用上了 → 再给 2 个
    expect(buffPortCount(4, 3)).toBe(6);
    expect(buffPortCount(0, 0)).toBe(0);      // 武器：没有输入端口
  });

  it("整组端口以标记牌中心等距展开（1 个时正好在中间，多个时也不偏）", () => {
    const nums = (count: number) =>
      Array.from({ length: count }, (_, i) => Number.parseFloat(portOffset(i, count, 78, 20)));
    expect(nums(1)).toEqual([78]);           // 单个端口就在标记牌中心
    expect(nums(3)).toEqual([58, 78, 98]);   // 3 个：中心两侧各 20px
    expect(nums(5)).toEqual([38, 58, 78, 98, 118]);
    // 一整组的几何中心始终落在标记牌中心上
    for (const n of [1, 3, 5, 7]) {
      const list = nums(n);
      expect((list[0] + list[list.length - 1]) / 2).toBeCloseTo(78);
    }
    // 像素写法（百分比会按整个角色节点解析 → 跑到整片区域正中）
    expect(portOffset(0, 3, 78, 20)).toMatch(/px$/);
  });

  it("极端情况下不会把端口推到卡片外面（保留 10px 边距）", () => {
    expect(portOffset(0, 30, 78, 20)).toBe("10px");   // 算出来是负的 → 夹到 10px
  });
});
