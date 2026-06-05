import "./ui.css";
import { getProject, getCases, getMask } from "./api";
import { initCornerstone } from "./cornerstone-init";
import type { ToolName } from "./tools";

function showBanner(msg: string) {
  const app = document.getElementById("app")!;
  const b = document.createElement("div");
  b.className = "banner";
  b.textContent = msg;
  app.appendChild(b);
  setTimeout(() => b.remove(), 8000);
}

async function main() {
  let currentCaseId: string | null = null;
  let activeLabelId = 1;
  let loading = false;

  const app = document.getElementById("app")!;
  app.innerHTML = `
    <div class="topbar">
      <strong>dicom_annotator</strong>
      <span id="case-counter" class="counter"></span>
      <span style="flex:1"></span>
      <button id="prev-btn">◀ Prev</button>
      <button id="next-btn">Next ▶</button>
      <span class="dirty-dot" id="dirty" title="unsaved changes"></span>
      <button class="primary" id="save-btn">Save</button>
    </div>
    <div class="main">
      <div class="case-panel">
        <input id="case-filter" class="filter" placeholder="Filter cases…" />
        <div class="case-list" id="case-list">Loading…</div>
      </div>
      <div class="viewports">
        <div class="viewport" id="vp-t2"></div>
        <div class="viewport" id="vp-adc"></div>
        <div class="viewport" id="vp-calc"></div>
      </div>
      <div class="tools-panel" id="tools">Tools</div>
    </div>
  `;
  await initCornerstone();

  // Cornerstone-coupled modules are imported after init so they don't touch the
  // engine before it is ready.
  const seg = await import("./segmentation");
  const toolsMod = await import("./tools");
  const scrub = await import("./scrubber");
  const prop = await import("./propagate");
  const vps = await import("./viewports");
  const { onDirtyChange, isDirty: getDirty, markClean } = await import("./dirty");

  const project = await getProject();
  activeLabelId = project.labels[0].id;
  document.querySelector(".topbar strong")!.textContent = `dicom_annotator — ${project.name}`;

  const cases = await getCases();
  const list = document.getElementById("case-list")!;
  list.innerHTML = cases
    .map(
      (c) =>
        `<div class="case-row ${c.annotated ? "annotated" : ""}" data-id="${c.id}">${c.id}</div>`
    )
    .join("");
  const caseRows = Array.from(list.querySelectorAll<HTMLDivElement>(".case-row"));
  const counter = document.getElementById("case-counter")!;

  // --- Case filter ---
  const filter = document.getElementById("case-filter") as HTMLInputElement;
  filter.addEventListener("input", () => {
    const q = filter.value.trim().toLowerCase();
    for (const r of caseRows) {
      r.style.display = r.dataset.id!.toLowerCase().includes(q) ? "" : "none";
    }
  });

  function rowFor(caseId: string): HTMLDivElement | undefined {
    return caseRows.find((r) => r.dataset.id === caseId);
  }
  function setNavDisabled(disabled: boolean) {
    (document.getElementById("prev-btn") as HTMLButtonElement).disabled = disabled;
    (document.getElementById("next-btn") as HTMLButtonElement).disabled = disabled;
    (document.getElementById("save-btn") as HTMLButtonElement).disabled = disabled;
  }
  function updateCounter() {
    const idx = currentCaseId ? caseRows.findIndex((r) => r.dataset.id === currentCaseId) : -1;
    counter.textContent = idx >= 0 ? `${idx + 1} / ${caseRows.length}` : `— / ${caseRows.length}`;
  }
  updateCounter();

  async function selectCase(caseId: string) {
    if (loading || caseId === currentCaseId) return;
    if (currentCaseId && getDirty()) {
      if (!confirm("You have unsaved changes. Discard them and switch case?")) return;
    }
    const row = rowFor(caseId);
    if (!row) return;

    loading = true;
    setNavDisabled(true);
    caseRows.forEach((r) => r.classList.remove("active"));
    row.classList.add("active", "loading");
    currentCaseId = caseId;
    updateCounter();

    try {
      const detail = await (await import("./api")).getCase(caseId);
      const modalitySlots = [
        { key: "t2",   viewportId: "vp-t2",   element: document.getElementById("vp-t2")   as HTMLDivElement },
        { key: "adc",  viewportId: "vp-adc",  element: document.getElementById("vp-adc")  as HTMLDivElement },
        { key: "calc", viewportId: "vp-calc", element: document.getElementById("vp-calc") as HTMLDivElement },
      ];
      const present = modalitySlots.filter((m) => detail.modalities.includes(m.key));
      await vps.loadCaseIntoViewports({ caseId, modalities: present });

      const viewportIds = present.map((p) => p.viewportId);
      toolsMod.createToolGroupOnce(viewportIds);
      await seg.ensureSegmentationVolume(`cornerstoneStreamingImageVolume:${caseId}:t2`);
      await seg.bindSegmentationToToolGroup(viewportIds);
      seg.clearSegmentationVolume();
      seg.installDirtyTracker();
      seg.setActiveSegmentIndex(activeLabelId);

      // Slice scrubber (recreate per case).
      const scrubberHost = document.querySelector(".viewports")!.parentElement!;
      scrubberHost.querySelector(".scrubber-host")?.remove();
      const host = document.createElement("div");
      host.className = "scrubber-host";
      scrubberHost.appendChild(host);
      scrub.attachScrubber({ hostEl: host, viewportIds, sliceCount: detail.slice_count });
      host.querySelector("#propagate-btn")!.addEventListener("click", () => {
        prop.propagateFromPrevious(scrub.currentSlice(viewportIds[0]), activeLabelId);
      });

      // Load any existing masks for every label.
      const refShape = detail.reference_shape;
      for (const lbl of project.labels) {
        const env = await getMask(caseId, lbl.id);
        if (!env) continue;
        if (env.shape.some((v, i) => v !== refShape[i])) {
          // Wrong-shaped mask would land in the wrong voxels — skip, don't corrupt.
          showBanner(`Skipped ${lbl.name}: stored mask ${env.shape.join("×")} ≠ case ${refShape.join("×")}`);
          continue;
        }
        await seg.populateFromEnvelope(env, lbl.id);
        if (env.warnings?.length) showBanner(env.warnings.join(" / "));
      }
      // Freshly-loaded case is clean: populate triggers volume.modified (which the
      // dirty tracker observes), so reset after loading rather than before.
      markClean();
    } catch (err) {
      showBanner(`Failed to load ${caseId}: ${(err as Error).message ?? err}`);
    } finally {
      row.classList.remove("loading");
      loading = false;
      setNavDisabled(false);
    }
  }

  caseRows.forEach((row) => {
    row.addEventListener("click", () => void selectCase(row.dataset.id!));
  });

  // --- Tools panel ---
  const tools = document.getElementById("tools")!;
  tools.innerHTML = `
    <div><strong>Tools</strong></div>
    <div class="tool-grid">
      <button data-tool="brush"   class="active">Brush</button>
      <button data-tool="erase">Erase</button>
      <button data-tool="polygon">Rect</button>
      <button data-tool="pan">Pan</button>
      <button data-tool="zoom">Zoom</button>
    </div>
    <div style="margin-top:10px">
      <div>Brush size: <span id="brush-size-val">6</span> px</div>
      <input type="range" min="1" max="40" value="6" id="brush-size">
    </div>
    <div style="margin-top:10px">
      <strong>Labels</strong>
      <div id="label-list"></div>
    </div>
    <div class="cheat" style="margin-top:12px">
      <strong>Shortcuts</strong>
      <div class="cheat-rows">
        <span><kbd>B</kbd> brush</span><span><kbd>E</kbd> erase</span>
        <span><kbd>P</kbd> rect</span><span><kbd>[</kbd> <kbd>]</kbd> size</span>
        <span><kbd>1</kbd>–<kbd>9</kbd> label</span><span><kbd>PgUp</kbd>/<kbd>PgDn</kbd> case</span>
        <span><kbd>⌘/Ctrl</kbd>+<kbd>S</kbd> save</span>
      </div>
    </div>
  `;

  const sizeInput = document.getElementById("brush-size") as HTMLInputElement;
  const sizeVal = document.getElementById("brush-size-val")!;
  function applyBrushSize(px: number) {
    const v = Math.max(1, Math.min(40, Math.round(px)));
    sizeInput.value = String(v);
    sizeVal.textContent = String(v);
    toolsMod.setBrushSize(v);
  }
  sizeInput.addEventListener("input", () => applyBrushSize(Number(sizeInput.value)));

  function selectTool(name: ToolName) {
    tools.querySelectorAll("button[data-tool]").forEach((b) =>
      b.classList.toggle("active", (b as HTMLElement).dataset.tool === name)
    );
    toolsMod.setActiveTool(name);
  }
  tools.querySelectorAll<HTMLButtonElement>("button[data-tool]").forEach((btn) => {
    btn.addEventListener("click", () => selectTool(btn.dataset.tool as ToolName));
  });

  // --- Labels ---
  const labelList = document.getElementById("label-list")!;
  labelList.innerHTML = project.labels
    .map(
      (l, i) =>
        `<div class="label-row ${i === 0 ? "active" : ""}" data-label-id="${l.id}">
           <span class="swatch" style="background:${l.color}"></span>${l.name} (${l.id})
         </div>`
    )
    .join("");
  function setActiveLabel(id: number) {
    activeLabelId = id;
    labelList.querySelectorAll<HTMLElement>(".label-row").forEach((r) =>
      r.classList.toggle("active", Number(r.dataset.labelId) === id)
    );
    seg.setActiveSegmentIndex(id);
  }
  labelList.querySelectorAll<HTMLElement>(".label-row").forEach((el) => {
    el.addEventListener("click", () => setActiveLabel(Number(el.dataset.labelId)));
  });

  // --- Dirty indicator ---
  const dirtyDot = document.getElementById("dirty")!;
  onDirtyChange(() => dirtyDot.classList.toggle("is-dirty", getDirty()));

  async function saveAll() {
    if (!currentCaseId || loading) return;
    setNavDisabled(true);
    try {
      const { putMask } = await import("./api");
      for (const lbl of project.labels) {
        await putMask(currentCaseId, lbl.id, seg.extractEnvelope(lbl.id));
      }
      markClean();
      rowFor(currentCaseId)?.classList.add("annotated");
      showBanner("Saved");
    } catch (err) {
      showBanner(`Save failed: ${(err as Error).message ?? err}`);
    } finally {
      setNavDisabled(false);
    }
  }
  document.getElementById("save-btn")!.addEventListener("click", saveAll);
  window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      void saveAll();
    }
  });

  // --- Case navigation ---
  function visibleRows(): HTMLDivElement[] {
    return caseRows.filter((r) => r.style.display !== "none");
  }
  function neighbour(offset: number): HTMLDivElement | undefined {
    const rows = visibleRows();
    const cur = rows.findIndex((r) => r.dataset.id === currentCaseId);
    if (cur === -1) return rows[0];
    return rows[cur + offset];
  }
  const goPrev = () => { const p = neighbour(-1); if (p) void selectCase(p.dataset.id!); };
  const goNext = () => { const n = neighbour(1);  if (n) void selectCase(n.dataset.id!); };
  document.getElementById("prev-btn")!.addEventListener("click", goPrev);
  document.getElementById("next-btn")!.addEventListener("click", goNext);

  const { installShortcuts } = await import("./shortcuts");
  installShortcuts({
    onTool: selectTool,
    onBrushDelta: (d) => applyBrushSize(Number(sizeInput.value) + d),
    onLabelIndex: (i) => { if (i < project.labels.length) setActiveLabel(project.labels[i].id); },
    onPrevCase: goPrev,
    onNextCase: goNext,
  });
}

main().catch((err) => {
  document.body.innerHTML = `<pre style="color:#fca5a5">${(err as Error).stack ?? err}</pre>`;
});
