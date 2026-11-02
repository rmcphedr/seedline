import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Compass } from "lucide-react";
import { OpportunityDetail } from "@/components/opportunity-detail";
import { publicApi, type Opportunity } from "@/lib/api";
import { demoEnabled } from "@/lib/demo-server";

export const dynamic = "force-dynamic";

export default async function ExploreDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let item: Opportunity;
  try { item = await publicApi<Opportunity>(`/public/opportunities/${id}`); }
  catch (error) { if (error instanceof Error && error.message.includes("not found")) notFound(); throw error; }
  return <div className="min-h-screen bg-[#f5f8f7]"><header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-5 sm:px-8"><Link href="/explore" className="flex items-center gap-2 text-xl font-bold tracking-tight"><span className="flex size-9 items-center justify-center rounded-xl bg-teal-800 text-white"><Compass size={21} aria-hidden="true" /></span>Seedline<span className="text-teal-700">.</span></Link><nav className="flex items-center gap-5 text-sm font-semibold"><Link href="/explore" className="text-teal-800 hover:underline">Explore funding</Link>{demoEnabled() && <Link href="/dashboard" className="text-teal-800 hover:underline">My profile</Link>}</nav></div></header><main className="mx-auto max-w-6xl px-5 py-10 sm:px-8"><Link href="/explore" className="inline-flex items-center gap-2 text-sm font-medium text-teal-800 hover:underline"><ArrowLeft size={16} aria-hidden="true" />Back to opportunities</Link><div className="my-8"><div className="mb-3 text-xs font-semibold uppercase tracking-widest text-teal-700">Verified funding opportunity</div><h1 className="max-w-4xl text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">{item.title}</h1><p className="mt-3 text-sm text-slate-500">Published {item.published_at ? new Date(item.published_at).toLocaleDateString("en-CA") : "recently"}</p></div>{demoEnabled() && <Link href={`/recommendations/${item.id}`} className="mb-7 inline-flex items-center rounded-xl bg-emerald-800 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-900">View match with my business →</Link>}<OpportunityDetail item={item}/></main></div>;
}
