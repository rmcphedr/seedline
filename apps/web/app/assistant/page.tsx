import { notFound } from "next/navigation";
import { AssistantWorkspace } from "@/components/assistant-workspace";
import { demoEnabled } from "@/lib/demo-server";

export const dynamic = "force-dynamic";

export default async function AssistantPage({ searchParams }: { searchParams: Promise<{ opportunity?: string }> }) {
  if (!demoEnabled()) notFound();
  const { opportunity } = await searchParams;
  const opportunityId = opportunity && /^[0-9a-f-]{36}$/i.test(opportunity) ? opportunity : undefined;
  return <AssistantWorkspace opportunityId={opportunityId}/>;
}
