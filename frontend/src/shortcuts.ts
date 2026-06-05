import type { ToolName } from "./tools";

export interface ShortcutHandlers {
  onTool: (t: ToolName) => void;
  onBrushDelta: (delta: number) => void;
  onLabelIndex: (index: number) => void;
  onPrevCase: () => void;
  onNextCase: () => void;
}

let installed = false;

export function installShortcuts(h: ShortcutHandlers): void {
  // Guard against double-install (e.g. if main() ever re-runs) so each keypress
  // fires its handler exactly once.
  if (installed) return;
  installed = true;

  window.addEventListener("keydown", (e) => {
    if ((e.target as HTMLElement)?.tagName === "INPUT") return;
    switch (e.key) {
      case "b": h.onTool("brush"); break;
      case "e": h.onTool("erase"); break;
      case "p": h.onTool("polygon"); break;
      case "[": h.onBrushDelta(-1); break;
      case "]": h.onBrushDelta(1); break;
      case "PageUp":   e.preventDefault(); h.onPrevCase(); break;
      case "PageDown": e.preventDefault(); h.onNextCase(); break;
      default:
        if (/^[1-9]$/.test(e.key)) h.onLabelIndex(Number(e.key) - 1);
    }
  });
}
