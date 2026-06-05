import { describe, it, expect, beforeEach, vi } from "vitest";
import { markDirty, markClean, isDirty, onDirtyChange } from "./dirty";

describe("dirty state", () => {
  beforeEach(() => {
    markClean(); // reset shared module state between tests
  });

  it("starts clean and flips on markDirty", () => {
    expect(isDirty()).toBe(false);
    markDirty();
    expect(isDirty()).toBe(true);
    markClean();
    expect(isDirty()).toBe(false);
  });

  it("fires listeners only on state transitions", () => {
    const fn = vi.fn();
    onDirtyChange(fn);
    markDirty();          // false -> true : fires
    markDirty();          // already dirty : no fire
    markClean();          // true -> false : fires
    markClean();          // already clean : no fire
    expect(fn).toHaveBeenCalledTimes(2);
  });
});
