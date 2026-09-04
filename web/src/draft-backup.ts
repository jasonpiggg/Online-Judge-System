export type CodeBackup = { code: string; revision: number };
export function readBackup(key: string): CodeBackup | null {
  const raw = sessionStorage.getItem(key) ?? localStorage.getItem(key);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw);
    if (typeof value.code === "string" && Number.isInteger(value.revision))
      return value;
  } catch {
    /* Preserve drafts written by earlier versions. */
  }
  return { code: raw, revision: -1 };
}
export function writeBackup(key: string, code: string, revision: number) {
  const raw = JSON.stringify({ code, revision });
  sessionStorage.setItem(key, raw);
  localStorage.setItem(key, raw);
}
export function clearBackup(key: string, code: string) {
  // An acknowledgement from one tab must not erase another tab's unsaved work.
  for (const storage of [sessionStorage, localStorage]) {
    const raw = storage.getItem(key);
    if (raw) {
      try {
        if (JSON.parse(raw).code === code) storage.removeItem(key);
      } catch {
        /* legacy backup */
      }
    }
  }
}
