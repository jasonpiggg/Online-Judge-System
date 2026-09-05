const paths: Record<string, string> = {
  users:
    "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m18 0v-2a4 4 0 0 0-3-3.87M13 3.13a4 4 0 0 1 0 7.75M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  shield: "M12 3 3 7v5c0 5 9 10 9 10s9-5 9-10V7l-9-4Zm-4 9 3 3 5-6",
  arrow: "M5 12h14m-6-6 6 6-6 6",
  book: "M4 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-2H4V4Zm16 0h-4a3 3 0 0 0-3 3m0 14a4 4 0 0 1 4-2h3V4Z",
  code: "m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18",
  check: "m5 12 4 4L19 6",
  cross: "m6 6 12 12M18 6 6 18",
  clock: "M12 8v4l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  spark: "m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3 3-7Z",
  search: "m21 21-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z",
  chart: "M4 3v17h17M8 15v-3m5 3V8m5 7V5",
  chevronLeft: "m15 18-6-6 6-6",
  chevronRight: "m9 18 6-6-6-6",
  close: "m7 7 10 10M17 7 7 17",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Zm0 0v6h6M8 13h8M8 17h6",
  play: "m8 5 11 7-11 7V5Z",
  bot: "M12 3v3M8 3h8M5 9h14a2 2 0 0 1 2 2v8H3v-8a2 2 0 0 1 2-2Zm3 4h.01M16 13h.01M8 17h8",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  info: "M12 17v-6m0-4h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  eye: "M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
  eyeOff: "m3 3 18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.9 5.2A11 11 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-2.1 3.1M6.2 6.2C3.5 8 2 12 2 12s3.5 7 10 7a10 10 0 0 0 4.2-.9",
  newTab: "M14 3h7v7m0-7-9 9M11 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-6",
};
export function Icon({ name = "spark" }: { name?: string }) {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] || paths.spark} />
    </svg>
  );
}
