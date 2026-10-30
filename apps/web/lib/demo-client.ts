import type { DemoContext } from "@/lib/demo-types";

export async function demoRequest<T>(path: string, method: "GET" | "POST" | "PATCH" = "GET", body?: object): Promise<T> {
  const response = await fetch(`/api/demo/${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : method === "POST" || method === "PATCH" ? "{}" : undefined,
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(typeof payload.detail === "string" ? payload.detail : `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function loadDemo(): Promise<DemoContext> { return demoRequest<DemoContext>("context"); }
