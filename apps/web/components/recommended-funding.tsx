"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Sparkles } from "lucide-react";
import { demoRequest } from "@/lib/demo-client";
import { RecommendationCard } from "@/components/recommendation-card";
import { FIELD_LABELS, profileHref, type RecommendationList } from "@/lib/recommendations";

export function RecommendedFunding() {
  const [data, setData] = useState<RecommendationList | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { demoRequest<RecommendationList>("recommendations").then(setData).catch(cause => setError(cause instanceof Error ? cause.message : "Could not load recommendations")); }, []);
  const top = (data?.items ?? []).filter(item => item.relevance_score !== null && item.relevance_score >= 20 && item.eligibility_status !== "potentially_ineligible").slice(0, 2);
  return <section className="rounded-[1.5rem] border border-emerald-200 bg-white p-6 shadow-sm sm:p-7"><div className="flex flex-wrap items-start justify-between gap-3"><div><Sparkles size={22} className="text-emerald-700"/><h2 className="mt-3 text-xl font-semibold">Recommended Funding Opportunities</h2><p className="mt-2 text-sm leading-6 text-slate-600">Ranked from your saved profile and verified, published funding records.</p></div>{data?.ready && <div className="rounded-xl bg-emerald-50 px-4 py-2 text-center"><div className="text-2xl font-bold text-emerald-900">{data.potentially_relevant_count}</div><div className="text-xs text-emerald-800">potentially relevant</div></div>}</div>
    {!data && !error && <p className="mt-5 text-sm text-slate-500">Checking opportunities…</p>}
    {error && <p role="alert" className="mt-5 rounded-xl bg-rose-50 p-4 text-sm text-rose-800">{error}</p>}
    {data && !data.ready && <div className="mt-5 rounded-xl bg-amber-50 p-5"><p className="text-sm font-semibold text-amber-950">Add a few business basics to unlock recommendations.</p><p className="mt-1 text-sm text-amber-900">We need {data.missing_profile_fields.map(field => FIELD_LABELS[field] ?? field.replaceAll("_", " ")).join(", ").toLowerCase()}.</p><Link href={profileHref(data.missing_profile_fields[0])} className="mt-3 inline-flex items-center gap-1 text-sm font-bold text-emerald-800 hover:underline">Update profile <ArrowRight size={15}/></Link></div>}
    {data?.ready && (top.length ? <div className="mt-6 grid gap-4 md:grid-cols-2">{top.map(item => <RecommendationCard key={item.opportunity.id} item={item}/>)}</div> : <div className="mt-5 rounded-xl bg-slate-50 p-5 text-sm text-slate-600">No strong potential matches are available from the currently published records. You can still review every assessment or browse public funding.</div>)}
    {data?.ready && <Link href="/recommendations" className="mt-6 inline-flex items-center gap-2 rounded-xl bg-emerald-800 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-900">View all recommendations <ArrowRight size={16}/></Link>}
  </section>;
}
