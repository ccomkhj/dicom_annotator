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
  const app = document.getElementById("app")!;
  app.innerHTML = `
    <div class="topbar">
      <strong>dicom_annotator</strong>
      <span class="dirty-dot" id="dirty"></span>
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
      (window as any).__createToolGroupOnce(viewportIds);
      const { ensureSegmentationVolume, bindSegmentationToToolGroup, setActiveSegmentIndex: setActive } =
        await import("./segmentation");
      await ensureSegmentationVolume(`cornerstoneStreamingImageVolume:${caseId}:t2`);
      await bindSegmentationToToolGroup(viewportIds);
      setActive(project.labels[0].id);

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

  const { setActiveTool, setBrushSize, createToolGroup } = await import("./tools");
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

  // Tool group is created lazily on first case load (after viewports exist).
  (window as any).__createToolGroupOnce = (viewportIds: string[]) => {
    if ((window as any).__toolGroupReady) return;
    createToolGroup(viewportIds);
    (window as any).__toolGroupReady = true;
  };
}

main().catch((err) => {
  document.body.innerHTML = `<pre style="color:#fca5a5">${(err as Error).stack ?? err}</pre>`;
});
