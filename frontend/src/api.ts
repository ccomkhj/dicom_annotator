import type { Project, CaseSummary, CaseDetail, MaskEnvelope } from "./types";

export async function getProject(): Promise<Project> {
  const r = await fetch("/api/project");
  if (!r.ok) throw new Error("project fetch failed");
  return r.json();
}

export async function getCases(): Promise<CaseSummary[]> {
  const r = await fetch("/api/cases");
  if (!r.ok) throw new Error("cases fetch failed");
  return r.json();
}

export async function getCase(id: string): Promise<CaseDetail> {
  const r = await fetch(`/api/cases/${id}`);
  if (!r.ok) throw new Error(`case ${id} fetch failed`);
  return r.json();
}

export async function getMask(caseId: string, labelId: number): Promise<MaskEnvelope | null> {
  const r = await fetch(`/api/cases/${caseId}/masks/${labelId}`);
  if (r.status === 404) return null;
  if (!r.ok) throw new Error("mask fetch failed");
  return r.json();
}

export async function putMask(
  caseId: string,
  labelId: number,
  env: MaskEnvelope,
): Promise<{ saved_at: number; sha256: string; bytes: number }> {
  const r = await fetch(`/api/cases/${caseId}/masks/${labelId}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(env),
  });
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error((body as { message?: string }).message ?? "mask save failed");
  }
  return r.json();
}
