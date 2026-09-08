import { queryOptions, useQuery } from "@tanstack/react-query";
import { api } from "./api";
export type Language = {
  name: string;
  file_ext: string;
  compile_cmd: string | null;
  run_cmd: string;
  time_limit: number;
  memory_limit: number;
};
export const languageOptions = queryOptions({
  queryKey: ["language-details"],
  queryFn: () =>
    api<{ name: string[]; languages: Language[] }>(
      "/languages/?include_metadata=true",
    ),
  staleTime: 0,
  refetchOnMount: "always",
  refetchOnWindowFocus: "always",
});
export const useLanguages = () => useQuery(languageOptions);
export function fileLanguages(name: string, languages: Language[]) {
  const extension = name.slice(name.lastIndexOf(".")).toLowerCase();
  return languages.filter(
    (language) => language.file_ext.toLowerCase() === extension,
  );
}
export function languageAccept(languages: Language[]) {
  return [
    ...new Set(languages.map((language) => language.file_ext.toLowerCase())),
  ]
    .sort()
    .join(",");
}
