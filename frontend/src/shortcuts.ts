import { setActiveTool, setBrushSize } from "./tools";
import { setActiveSegmentIndex } from "./segmentation";

export function installShortcuts(labelIds: number[], onPrevCase: () => void, onNextCase: () => void) {
  window.addEventListener("keydown", e => {
    if ((e.target as HTMLElement)?.tagName === "INPUT") return;
    switch (e.key) {
      case "b": setActiveTool("brush"); break;
      case "e": setActiveTool("erase"); break;
      case "p": setActiveTool("polygon"); break;
      case "[": setBrushSize(Math.max(1, getBrushSize() - 1)); break;
      case "]": setBrushSize(getBrushSize() + 1); break;
      case "PageUp":   onPrevCase(); break;
      case "PageDown": onNextCase(); break;
      default:
        if (/^[1-9]$/.test(e.key)) {
          const idx = Number(e.key) - 1;
          if (idx < labelIds.length) setActiveSegmentIndex(labelIds[idx]);
        }
    }
  });
}

function getBrushSize(): number {
  const el = document.getElementById("brush-size") as HTMLInputElement | null;
  return el ? Number(el.value) : 6;
}
