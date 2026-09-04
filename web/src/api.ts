import { QueryClient } from "@tanstack/react-query";
let activeUser: string | undefined;
export const setApiUser = (id?: string) => {
  activeUser = id;
};
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: 15000, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
});
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    credentials: "same-origin",
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(activeUser && !path.startsWith("/auth/")
        ? { "X-OJ-User": activeUser }
        : {}),
      ...options.headers,
    },
  });
  const value = await response.json();
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/auth/"))
      window.dispatchEvent(new Event("session-expired"));
    throw new ApiError(response.status, value.msg || "请求失败，请重试");
  }
  return value.data as T;
}
export const json = (method: string, data?: unknown): RequestInit => ({
  method,
  body: data === undefined ? undefined : JSON.stringify(data),
});
export const errorText = (e: unknown) =>
  e instanceof Error ? e.message : "请求失败，请重试";
