import { NextRequest, NextResponse } from "next/server";
import { demoEnabled } from "@/lib/demo-server";

const allowed = new Set(["create", "example", "reset", "context", "summary", "founder", "organization", "funding-intent", "details", "interests", "onboarding", "completion"]);
type Context = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, { params }: Context) {
  if (!demoEnabled()) return new NextResponse("Not found", { status: 404 });
  const { path } = await params;
  if (path.length !== 1 || !allowed.has(path[0])) return new NextResponse("Not found", { status: 404 });
  const method = request.method;
  if ((["create", "example", "reset"].includes(path[0]) && method !== "POST") ||
      (["context", "summary", "completion"].includes(path[0]) && method !== "GET") ||
      (!(["create", "example", "reset", "context", "summary", "completion"].includes(path[0])) && !["GET", "PATCH"].includes(method))) {
    return new NextResponse("Method not allowed", { status: 405 });
  }
  try {
    const headers = new Headers({ "Content-Type": "application/json" });
    const cookie = request.cookies.get("seedline_demo")?.value;
    if (cookie) headers.set("Cookie", `seedline_demo=${cookie}`);
    const backend = await fetch(`${process.env.API_BASE_URL ?? "http://localhost:8000"}/api/demo/${path[0]}`, {
      method, headers, body: method === "POST" || method === "PATCH" ? await request.text() || "{}" : undefined,
      cache: "no-store",
    });
    const response = new NextResponse(await backend.text(), {
      status: backend.status,
      headers: { "Content-Type": backend.headers.get("content-type") ?? "application/json", "Cache-Control": "no-store" },
    });
    const setCookie = backend.headers.get("set-cookie");
    const token = setCookie?.match(/(?:^|\s)seedline_demo=([^;]+)/)?.[1];
    if (token) response.cookies.set("seedline_demo", token, { httpOnly: true, sameSite: "lax", secure: false, maxAge: 7 * 24 * 3600, path: "/" });
    return response;
  } catch {
    return NextResponse.json({ detail: "Seedline demo API is unavailable. Start the local services and retry." }, { status: 503 });
  }
}

export { forward as GET, forward as POST, forward as PATCH };
