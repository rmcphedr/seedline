import { timingSafeEqual } from "node:crypto";

export function validAdminAuthorization(authorization: string | null): boolean {
  const secret = process.env.ADMIN_API_KEY;
  if (!secret || !authorization?.startsWith("Basic ")) return false;
  try {
    const decoded = Buffer.from(authorization.slice(6), "base64").toString("utf8");
    const provided = Buffer.from(decoded);
    const expected = Buffer.from(`admin:${secret}`);
    return provided.length === expected.length && timingSafeEqual(provided, expected);
  } catch {
    return false;
  }
}
