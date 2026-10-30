import { notFound } from "next/navigation";
import { ProfileDashboard } from "@/components/profile-dashboard";
import { demoEnabled } from "@/lib/demo-server";

export const dynamic = "force-dynamic";
export default function DashboardPage() {
  if (!demoEnabled()) notFound();
  return <ProfileDashboard/>;
}
