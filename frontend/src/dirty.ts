let dirty = false;
const listeners = new Set<() => void>();

export function markDirty(): void {
  if (!dirty) { dirty = true; listeners.forEach(l => l()); }
}

export function markClean(): void {
  if (dirty) { dirty = false; listeners.forEach(l => l()); }
}

export function isDirty(): boolean { return dirty; }

export function onDirtyChange(fn: () => void): void { listeners.add(fn); }

window.addEventListener("beforeunload", e => {
  if (dirty) { e.preventDefault(); e.returnValue = ""; }
});
