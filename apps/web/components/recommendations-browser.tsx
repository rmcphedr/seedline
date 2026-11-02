"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Compass, Leaf } from "lucide-react";
import { demoRequest } from "@/lib/demo-client";
import { OPTIONS } from "@/lib/demo-types";
import { RecommendationCard } from "@/components/recommendation-card";
import { FIELD_LABELS, STATUS_LABELS, profileHref, type RecommendationList } from "@/lib/recommendations";

const selectClass = "h-11 rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-800 outline-none focus:border-emerald-700";

export function RecommendationsBrowser() {
  const [data, setData] = useState<RecommendationList | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("all");
  const [fundingType, setFundingType] = useState("all");
  const [industry, setIndustry] = useState("all");
  const [deadline, setDeadline] = useState("all");
  const [asOf, setAsOf] = useState<number | null>(null);
  useEffect(() => { demoRequest<RecommendationList>("recommendations").then(result => { setAsOf(Date.now()); setData(result); }).catch(cause => setError(cause instanceof Error ? cause.message : "Could not load recommendations")); }, []);

  const filtered = (data?.items ?? []).filter(item => {
    if (status !== "all" && item.eligibility_status !== status) return false;
    if (fundingType !== "all" && item.opportunity.funding_type !== fundingType) return false;
    if (industry !== "all" && !item.industry_tags.includes(industry)) return false;
    if (deadline === "confirmed" && !item.deadline || deadline === "unconfirmed" && item.deadline) return false;
    if (deadline === "next30") {
      if (!item.deadline || asOf === null || new Date(item.deadline).getTime() > asOf + 30 * 86400000) return false;
    }
    return true;
  });

  return <div className="min-h-screen bg-[#f6f8f5] text-slate-900">
    <header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 sm:px-8"><Link href="/explore" className="flex items-center gap-2 text-xl font-bold"><span className="grid size-9 place-items-center rounded-xl bg-emerald-800 text-white"><Leaf size={20}/></span>Seedline<span className="text-emerald-700">.</span></Link><nav className="flex gap-5 text-sm font-semibold"><Link href="/dashboard" className="text-slate-600 hover:text-emerald-800">My profile</Link><Link href="/explore" className="text-slate-600 hover:text-emerald-800">Public explorer</Link></nav></div></header>
    <main className="mx-auto max-w-7xl px-5 pb-20 pt-10 sm:px-8"><Link href="/dashboard" className="inline-flex items-center gap-1 text-sm font-semibold text-emerald-800 hover:underline"><ArrowLeft size={15}/>Back to dashboard</Link><div className="mt-7 flex flex-wrap items-end justify-between gap-5"><div><p className="text-xs font-bold uppercase tracking-widest text-emerald-700">Your funding search</p><h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Recommended Funding Opportunities</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">Ranked against your saved business profile. Eligibility reflects only requirements we can read from the funding record and is never a guarantee.</p></div>{data?.ready && <div className="rounded-2xl bg-white px-5 py-3 text-center shadow-sm"><div className="text-2xl font-bold text-emerald-800">{data.potentially_relevant_count}</div><div className="text-xs text-slate-500">potentially relevant</div></div>}</div>
      {error && <div role="alert" className="mt-7 rounded-xl bg-rose-50 p-5 text-sm text-rose-800">{error} <Link href="/demo" className="font-bold underline">Start a demo profile</Link></div>}
      {!data && !error && <p className="mt-8 text-sm text-slate-500">Assessing published opportunities…</p>}
      {data && !data.ready && <div className="mt-8 rounded-[1.5rem] border border-amber-200 bg-white p-7"><Compass size={26} className="text-amber-700"/><h2 className="mt-4 text-xl font-semibold">Add a few business basics first</h2><p className="mt-2 text-sm text-slate-600">We need your business country, industry and funding purpose before ranking opportunities. Your profile completion percentage is separate from these matching inputs.</p><div className="mt-5 flex flex-wrap gap-2">{data.missing_profile_fields.map(field => <Link key={field} href={profileHref(field)} className="rounded-lg bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-900 hover:bg-amber-100">Add {FIELD_LABELS[field] ?? field.replaceAll("_", " ")} →</Link>)}</div></div>}
      {data?.ready && <><div className="mt-8 grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 sm:grid-cols-2 lg:grid-cols-4">
        <label className="grid gap-1.5 text-xs font-semibold text-slate-600">Eligibility<select aria-label="Eligibility filter" className={selectClass} value={status} onChange={event => setStatus(event.target.value)}><option value="all">All assessments</option>{Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="grid gap-1.5 text-xs font-semibold text-slate-600">Funding type<select aria-label="Funding type filter" className={selectClass} value={fundingType} onChange={event => setFundingType(event.target.value)}><option value="all">All funding types</option>{["grant", "loan", "investment", "competition", "procurement"].map(value => <option key={value} value={value}>{value}</option>)}</select></label>
        <label className="grid gap-1.5 text-xs font-semibold text-slate-600">Industry<select aria-label="Industry filter" className={selectClass} value={industry} onChange={event => setIndustry(event.target.value)}><option value="all">All industries</option>{OPTIONS.industry.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="grid gap-1.5 text-xs font-semibold text-slate-600">Application deadline<select aria-label="Deadline filter" className={selectClass} value={deadline} onChange={event => setDeadline(event.target.value)}><option value="all">Any deadline</option><option value="next30">Within 30 days</option><option value="confirmed">Confirmed deadline</option><option value="unconfirmed">Deadline unconfirmed</option></select></label>
      </div><div className="mt-6 flex items-center justify-between"><p className="text-sm text-slate-600">{filtered.length} opportunit{filtered.length === 1 ? "y" : "ies"}</p><Link href="/onboarding?step=business_overview" className="inline-flex items-center gap-1 text-sm font-semibold text-emerald-800 hover:underline">Update profile <ArrowRight size={15}/></Link></div>
      {filtered.length ? <div className="mt-5 grid gap-5 md:grid-cols-2 xl:grid-cols-3">{filtered.map(item => <RecommendationCard key={item.opportunity.id} item={item}/>)}</div> : <div className="mt-5 rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center"><Compass size={28} className="mx-auto text-emerald-700"/><h2 className="mt-3 text-lg font-semibold">No opportunities match these filters</h2><p className="mt-2 text-sm text-slate-600">Try broadening the filters or browse all verified funding.</p><Link href="/explore" className="mt-4 inline-block text-sm font-bold text-emerald-800 hover:underline">Open public explorer →</Link></div>}</>}
    </main>
  </div>;
}
