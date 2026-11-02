import { notFound } from "next/navigation";
import { RecommendationDetail } from "@/components/recommendation-detail";
import { demoEnabled } from "@/lib/demo-server";

export const dynamic = "force-dynamic";
export default async function RecommendationPage({ params }: { params: Promise<{ id: string }> }) {
  if (!demoEnabled()) notFound();
  const { id } = await params;
  return <RecommendationDetail id={id}/>;
}
