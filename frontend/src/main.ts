import "./ui.css";
import { getProject, getCases, getMask } from "./api";
import { initCornerstone } from "./cornerstone-init";

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
  const app = document.getElementById("app")!;
  app.innerHTML = `
    <div class="topbar">
      <strong>dicom_annotator</strong>
      <span style="flex:1"></span>
      <button id="prev-btn">◀ Prev</button>
      <button id="next-btn">Next ▶</button>
      <span class="dirty-dot" id="dirty"></span>
      <button class="primary" id="save-btn">Save</button>
    </div>
    <div class="main">
      <div class="case-list" id="case-list">Loading…</div>
      <div class="viewports">
        <div class="viewport" id="vp-t2"></div>
        <div class="viewport" id="vp-adc"></div>
        <div class="viewport" id="vp-calc"></div>
      </div>
      <div class="tools-panel" id="tools">Tools</div>
    </div>
  `;
  await initCornerstone();
  const project = await getProject();
  document.querySelector(".topbar strong")!.textContent = `dicom_annotator — ${project.name}`;
  const cases = await getCases();
  const list = document.getElementById("case-list")!;
  list.innerHTML = cases
    .map(
      (c) =>
        `<div class="case-row ${c.annotated ? "annotated" : ""}" data-id="${c.id}">${c.id}</div>`
    )
    .join("");
  list.querySelectorAll<HTMLDivElement>(".case-row").forEach((row) => {
    row.addEventListener("click", async () => {
      list.querySelectorAll(".case-row").forEach(r => r.classList.remove("active"));
      row.classList.add("active");
      const caseId = row.dataset.id!;
      currentCaseId = caseId;
      // Probe the case for available modalities
      const detail = await (await fetch(`/api/cases/${caseId}`)).json();
      const modalitySlots = [
        { key: "t2",   viewportId: "vp-t2",   element: document.getElementById("vp-t2")   as HTMLDivElement },
        { key: "adc",  viewportId: "vp-adc",  element: document.getElementById("vp-adc")  as HTMLDivElement },
        { key: "calc", viewportId: "vp-calc", element: document.getElementById("vp-calc") as HTMLDivElement },
      ];
      const present = modalitySlots.filter(m => detail.modalities.includes(m.key));
      await (await import("./viewports")).loadCaseIntoViewports({ caseId, modalities: present });

      const viewportIds = present.map(p => p.viewportId);
      (await import("./tools")).createToolGroupOnce(viewportIds);
      const { ensureSegmentationVolume, bindSegmentationToToolGroup, setActiveSegmentIndex: setActive } =
        await import("./segmentation");
      await ensureSegmentationVolume(`cornerstoneStreamingImageVolume:${caseId}:t2`);
      await bindSegmentationToToolGroup(viewportIds);
      const { clearSegmentationVolume } = await import("./segmentation");
      clearSegmentationVolume();
      (await import("./segmentation")).installDirtyTracker();
      setActive(project.labels[0].id);

      const { attachScrubber, currentSlice } = await import("./scrubber");
      const { propagateFromPrevious } = await import("./propagate");
      const scrubberHost = document.querySelector(".viewports")!.parentElement!;
      const existing = scrubberHost.querySelector(".scrubber-host");
      if (existing) existing.remove();
      const host = document.createElement("div");
      host.className = "scrubber-host";
      scrubberHost.appendChild(host);
      attachScrubber({
        hostEl: host,
        viewportIds,
        sliceCount: detail.slice_count,
      });
      host.querySelector("#propagate-btn")!.addEventListener("click", () => {
        const idx = currentSlice(viewportIds[0]);
        const activeLabelEl = document.querySelector(".case-row.active[data-label-id]") as HTMLElement | null;
        const activeLabel = Number(activeLabelEl?.dataset.labelId ?? "1");
        propagateFromPrevious(idx, activeLabel);
      });

      for (const lbl of project.labels) {
        const env = await getMask(caseId, lbl.id);
        if (env) {
          const { populateFromEnvelope } = await import("./segmentation");
          await populateFromEnvelope(env, lbl.id);
          if (env.warnings?.length) showBanner(env.warnings.join(" / "));
        }
      }
    });
  });

  // --- Tools panel ---
  const tools = document.getElementById("tools")!;
  tools.innerHTML = `
    <div><strong>Tools</strong></div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-top:6px">
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
  `;
  const labelList = document.getElementById("label-list")!;
  labelList.innerHTML = project.labels.map((l, i) =>
    `<div class="case-row ${i === 0 ? "active" : ""}" data-label-id="${l.id}">
       <span style="display:inline-block;width:10px;height:10px;background:${l.color};margin-right:6px"></span>${l.name} (${l.id})
     </div>`
  ).join("");

  const { setActiveTool, setBrushSize } = await import("./tools");
  const { setActiveSegmentIndex } = await import("./segmentation");

  tools.querySelectorAll<HTMLButtonElement>("button[data-tool]").forEach(btn => {
    btn.addEventListener("click", () => {
      tools.querySelectorAll("button[data-tool]").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      setActiveTool(btn.dataset.tool as any);
    });
  });
  const sizeInput = document.getElementById("brush-size") as HTMLInputElement;
  const sizeVal = document.getElementById("brush-size-val")!;
  sizeInput.addEventListener("input", () => {
    sizeVal.textContent = sizeInput.value;
    setBrushSize(Number(sizeInput.value));
  });
  labelList.querySelectorAll<HTMLElement>(".case-row").forEach(el => {
    el.addEventListener("click", () => {
      labelList.querySelectorAll(".case-row").forEach(r => r.classList.remove("active"));
      el.classList.add("active");
      setActiveSegmentIndex(Number(el.dataset.labelId));
    });
  });

  // Dirty indicator
  const { onDirtyChange, isDirty: getDirty, markClean } = await import("./dirty");
  const dirtyDot = document.getElementById("dirty")!;
  onDirtyChange(() => dirtyDot.classList.toggle("is-dirty", getDirty()));

  async function saveAll() {
    if (!currentCaseId) return;
    try {
      const { extractEnvelope } = await import("./segmentation");
      const { putMask } = await import("./api");
      for (const lbl of project.labels) {
        const env = extractEnvelope(lbl.id);
        await putMask(currentCaseId, lbl.id, env);
      }
      markClean();
      showBanner("Saved");
    } catch (err) {
      showBanner(`Save failed: ${(err as Error).message ?? err}`);
    }
  }
  document.getElementById("save-btn")!.addEventListener("click", saveAll);
  window.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); saveAll(); }
  });

  const caseRows = Array.from(list.querySelectorAll<HTMLDivElement>(".case-row"));
  function currentCaseRow(): HTMLDivElement | undefined {
    return caseRows.find(r => r.classList.contains("active"));
  }
  function neighbour(offset: number): HTMLDivElement | undefined {
    const cur = currentCaseRow();
    if (!cur) return caseRows[0];
    const idx = caseRows.indexOf(cur);
    return caseRows[idx + offset];
  }
  const goPrev = () => { const p = neighbour(-1); if (p) p.click(); };
  const goNext = () => { const n = neighbour(1);  if (n) n.click(); };
  document.getElementById("prev-btn")!.addEventListener("click", goPrev);
  document.getElementById("next-btn")!.addEventListener("click", goNext);

  const { installShortcuts } = await import("./shortcuts");
  installShortcuts(project.labels.map(l => l.id), goPrev, goNext);
}

main().catch((err) => {
  document.body.innerHTML = `<pre style="color:#fca5a5">${(err as Error).stack ?? err}</pre>`;
});
