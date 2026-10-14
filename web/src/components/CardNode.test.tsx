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

  it("整组端口以 50% 为中心等距展开（1 个时正好在中间，多个时也不偏）", () => {
    const nums = (count: number) =>
      Array.from({ length: count }, (_, i) => Number.parseFloat(portOffset(i, count, 50, 4)));
    expect(nums(1)).toEqual([50]);           // 单个端口就在容器正中
    expect(nums(3)).toEqual([46, 50, 54]);   // 3 个：中心两侧各 4%
    expect(nums(5)).toEqual([42, 46, 50, 54, 58]);
    // 一整组的几何中心始终落在 50% 上
    for (const n of [1, 3, 5, 7]) {
      const list = nums(n);
      expect((list[0] + list[list.length - 1]) / 2).toBeCloseTo(50);
    }
    // 是百分比写法（卡片多宽都在中间那一带），不是像素
    expect(portOffset(0, 3, 50, 4)).toMatch(/%$/);
  });

  it("极端情况下不会把端口推到容器外面（保留 2% 边距）", () => {
    expect(portOffset(0, 30, 50, 4)).toBe("2%");     // 算出来是负的 → 夹到 2%
  });
});
