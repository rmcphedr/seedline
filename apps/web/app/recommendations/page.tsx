import { notFound } from "next/navigation";
import { RecommendationsBrowser } from "@/components/recommendations-browser";
import { demoEnabled } from "@/lib/demo-server";

export const dynamic = "force-dynamic";
export default function RecommendationsPage() {
  if (!demoEnabled()) notFound();
  return <RecommendationsBrowser/>;
}
