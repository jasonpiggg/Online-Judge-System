export function localTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : value + "Z");
  if (Number.isNaN(date.getTime())) return "—";
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(date);
  return parts;
}
