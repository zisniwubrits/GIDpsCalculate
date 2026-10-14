/**
 * 角色 / 武器卡片的**拐力端口**：入度一个点、出度一个点。
 *
 * 为什么单测在这里：jsdom 没有布局，端口落在哪只能靠"行内 left 的值"来验
 * （样式表另有一份基准位置，见 styles.test.ts 的契约用例）。
 *
 * 用户在真机上连续遇到"箭头落点和端口对不上"，最后定的口径是
 * **多个箭头可以往同一个点指**（不再按来源数量摆多个端口），所以这里锁两件事：
 *   1. 入度只有一个（多来源都汇聚到它，不会因为来源变多而重新展开）；
 *   2. 两个点都用百分比居中（入度正中、出度往右一档）。
 */
import { describe, expect, it } from "vitest";
import { ROLE_PORT_IN_LEFT, ROLE_PORT_OUT_LEFT } from "./CardNode";

const num = (s: string) => Number.parseFloat(s);

describe("拐力端口：一个入度点 + 一个出度点", () => {
  it("入度在容器正中，出度往右一档（都在中间那一带）", () => {
    const inLeft = num(ROLE_PORT_IN_LEFT);
    const outLeft = num(ROLE_PORT_OUT_LEFT);
    expect(ROLE_PORT_IN_LEFT).toMatch(/%$/);          // 百分比：卡片多宽都在中间
    expect(ROLE_PORT_OUT_LEFT).toMatch(/%$/);
    expect(inLeft).toBe(50);
    expect(outLeft).toBeGreaterThan(inLeft);
    expect(outLeft - inLeft).toBeLessThanOrEqual(10);  // 挨着，算"同一组"
    expect(outLeft).toBeLessThanOrEqual(60);
  });
});
