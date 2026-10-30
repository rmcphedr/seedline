import type { NextRequest } from "next/server";
import { validAdminAuthorization } from "@/lib/admin-key";

export function proxy(request: NextRequest) {
  if (!process.env.ADMIN_API_KEY) {
    return new Response("Admin access is not configured", { status: 503 });
  }
  if (!validAdminAuthorization(request.headers.get("authorization"))) {
    return new Response("Administrator sign-in required", {
      status: 401,
      headers: { "WWW-Authenticate": 'Basic realm="Bridge admin", charset="UTF-8"' },
    });
  }
}

export const config = { matcher: ["/", "/admin/:path*", "/opportunities/:path*"] };
