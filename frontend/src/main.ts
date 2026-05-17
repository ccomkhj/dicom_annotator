import "./ui.css";
import { getProject, getCases } from "./api";
import { initCornerstone } from "./cornerstone-init";
import { loadModalityIntoViewport } from "./viewports";

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
      list.querySelectorAll(".case-row").forEach((r) => r.classList.remove("active"));
      row.classList.add("active");
      const caseId = row.dataset["id"]!;
      await loadModalityIntoViewport({
        caseId,
        modality: "t2",
        viewportId: "vp-t2",
        element: document.getElementById("vp-t2") as HTMLDivElement,
      });
    });
  });
}

main().catch((err) => {
  document.body.innerHTML = `<pre style="color:#fca5a5">${(err as Error).stack ?? err}</pre>`;
});
