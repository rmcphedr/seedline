import { headers } from "next/headers";
import { validAdminAuthorization } from "./admin-key";

export async function requireAdmin(): Promise<void> {
  if (!validAdminAuthorization((await headers()).get("authorization"))) {
    throw new Error("Administrator authorization required");
  }
}
