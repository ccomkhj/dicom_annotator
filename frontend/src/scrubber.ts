import { renderingEngine } from "./cornerstone-init";

export function attachScrubber(args: {
  hostEl: HTMLElement;
  viewportIds: string[];
  sliceCount: number;
  onSliceChange?: (sliceIdx: number) => void;
}): void {
  const { hostEl, viewportIds, sliceCount, onSliceChange } = args;
  hostEl.innerHTML = `
    <div style="display:flex;gap:8px;align-items:center;padding:6px;background:#1f2937;border-radius:3px;margin-top:6px">
      <span>Slice <span id="slice-num">0</span> / ${sliceCount - 1}</span>
      <input type="range" min="0" max="${sliceCount - 1}" value="0" id="slice-input" style="flex:1">
      <button id="propagate-btn">↗ Propagate from prev</button>
    </div>
  `;
  const input = hostEl.querySelector("#slice-input") as HTMLInputElement;
  const num = hostEl.querySelector("#slice-num") as HTMLSpanElement;
  input.addEventListener("input", () => {
    const idx = Number(input.value);
    num.textContent = String(idx);
    for (const vid of viewportIds) {
      const vp = renderingEngine.getViewport(vid) as any;
      if (!vp) continue;
      if (typeof vp.setSliceIndex === "function") {
        vp.setSliceIndex(idx);
      } else if (typeof vp.setImageIdIndex === "function") {
        vp.setImageIdIndex(idx);
      }
      vp.render?.();
    }
    onSliceChange?.(idx);
  });
}

export function currentSlice(viewportId: string): number {
  const vp = renderingEngine.getViewport(viewportId) as any;
  if (!vp) return 0;
  if (typeof vp.getSliceIndex === "function") return vp.getSliceIndex();
  if (typeof vp.getCurrentImageIdIndex === "function") return vp.getCurrentImageIdIndex();
  return 0;
}
