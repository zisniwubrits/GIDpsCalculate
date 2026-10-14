/**
 * 角色 / 武器卡片的**拐力端口**：入度一个点、出度一个点。
 *
 * 为什么单测在这里：jsdom 没有布局，端口落在哪只能靠"行内 left 的值"来验
 * （样式表另有一份基准位置，见 styles.test.ts 的契约用例）。
 *
 * 用户在真机上连续遇到"箭头落点和端口对不上 / 整体右偏"，最后定的口径是：
 *   1. **多个箭头可以往同一个点指**（不再按来源数量摆多个端口）；
 *   2. 位置用**容器宽度百分比**，以 50% 那条线为准、**左右各一个**。
 */
import { describe, expect, it } from "vitest";
import { ROLE_PORT_IN_LEFT, ROLE_PORT_OUT_LEFT } from "./CardNode";

const num = (s: string) => Number.parseFloat(s);

describe("拐力端口：一个入度点 + 一个出度点，分居 50% 两侧", () => {
  it("入度在 50% 左边一档、出度正好在 50%（整组以 50% 为界）", () => {
    expect(ROLE_PORT_IN_LEFT).toMatch(/%$/);         // 百分比写法：卡片多宽都跟着走
    expect(ROLE_PORT_OUT_LEFT).toMatch(/%$/);
    const inLeft = num(ROLE_PORT_IN_LEFT);
    const outLeft = num(ROLE_PORT_OUT_LEFT);
    expect(outLeft).toBe(50);                        // 出度就压在 50% 这条线上
    expect(inLeft).toBeLessThan(outLeft);            // 入度在它左边
    expect(outLeft - inLeft).toBeLessThanOrEqual(10);  // 挨着，算"同一组"
    expect(inLeft).toBeGreaterThanOrEqual(40);       // 靠中间，不贴左边缘
  });
});
