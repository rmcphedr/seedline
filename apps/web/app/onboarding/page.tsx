import { notFound } from "next/navigation";
import { OnboardingWizard } from "@/components/onboarding-wizard";
import { demoEnabled } from "@/lib/demo-server";
import { SECTION_META, type SectionId } from "@/lib/demo-types";

export const dynamic = "force-dynamic";
export default async function OnboardingPage({ searchParams }: { searchParams: Promise<{ step?: string; fresh?: string; field?: string; returnTo?: string }> }) {
  if (!demoEnabled()) notFound();
  const { step, fresh, field, returnTo } = await searchParams;
  const initialStep = SECTION_META.some(section => section.id === step) ? step as SectionId : undefined;
  const safeReturn = returnTo && /^\/recommendations(?:\/[0-9a-f-]{36})?$/i.test(returnTo) ? returnTo : undefined;
  return <OnboardingWizard key={fresh ?? "default"} initialStep={initialStep} initialField={field} returnTo={safeReturn}/>;
}
