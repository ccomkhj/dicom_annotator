import * as csTools from "@cornerstonejs/tools";
import { TOOL_GROUP_ID } from "./segmentation";

const {
  BrushTool,
  RectangleScissorsTool,
  // NOTE: PolygonScissorsTool does not exist in @cornerstonejs/tools v1.77.
  // RectangleScissorsTool is used as the "polygon/selection" tool instead.
  PanTool,
  ZoomTool,
  StackScrollMouseWheelTool,
  ToolGroupManager,
} = csTools;

export type ToolName = "brush" | "erase" | "polygon" | "pan" | "zoom";

export function createToolGroup(viewportIds: string[]): void {
  // addTool is idempotent at the global level — guard against double-registration
  // across hot-reloads or repeated calls.
  const globalState = (csTools as any).state?.tools ?? {};
  if (!globalState[BrushTool.toolName]) csTools.addTool(BrushTool);
  if (!globalState[RectangleScissorsTool.toolName]) csTools.addTool(RectangleScissorsTool);
  if (!globalState[PanTool.toolName]) csTools.addTool(PanTool);
  if (!globalState[ZoomTool.toolName]) csTools.addTool(ZoomTool);
  if (!globalState[StackScrollMouseWheelTool.toolName]) csTools.addTool(StackScrollMouseWheelTool);

  const tg = ToolGroupManager.createToolGroup(TOOL_GROUP_ID)!;

  // BrushTool handles both fill and erase via activeStrategy config.
  // Default strategy is FILL_INSIDE_CIRCLE; erase switches to ERASE_INSIDE_CIRCLE.
  tg.addTool(BrushTool.toolName, { activeStrategy: "FILL_INSIDE_CIRCLE" });
  tg.addTool(RectangleScissorsTool.toolName);
  tg.addTool(PanTool.toolName);
  tg.addTool(ZoomTool.toolName);
  tg.addTool(StackScrollMouseWheelTool.toolName);

  for (const vid of viewportIds) {
    tg.addViewport(vid, "dicom-annotator-engine");
  }

  tg.setToolActive(StackScrollMouseWheelTool.toolName);
  setActiveTool("brush");
}

export function setActiveTool(name: ToolName): void {
  const tg = csTools.ToolGroupManager.getToolGroup(TOOL_GROUP_ID)!;
  if (!tg) return;

  // When switching to erase mode, reconfigure BrushTool strategy before activating.
  if (name === "erase") {
    tg.setToolConfiguration(BrushTool.toolName, { activeStrategy: "ERASE_INSIDE_CIRCLE" });
  } else if (name === "brush") {
    tg.setToolConfiguration(BrushTool.toolName, { activeStrategy: "FILL_INSIDE_CIRCLE" });
  }

  // Deactivate all left-button tools before activating the chosen one.
  for (const t of [
    BrushTool.toolName,
    RectangleScissorsTool.toolName,
    PanTool.toolName,
    ZoomTool.toolName,
  ]) {
    tg.setToolPassive(t);
  }

  const toolName = (
    {
      brush: BrushTool.toolName,
      erase: BrushTool.toolName, // same tool class, different activeStrategy
      polygon: RectangleScissorsTool.toolName, // PolygonScissorsTool not in v1.77
      pan: PanTool.toolName,
      zoom: ZoomTool.toolName,
    } as const
  )[name];

  tg.setToolActive(toolName, { bindings: [{ mouseButton: 1 }] });
}

export function setBrushSize(px: number): void {
  const tg = csTools.ToolGroupManager.getToolGroup(TOOL_GROUP_ID)!;
  if (!tg) return;
  tg.setToolConfiguration(BrushTool.toolName, { brushSize: px });
}
