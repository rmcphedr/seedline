"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, CircleHelp, Leaf } from "lucide-react";
import { OpportunityDetail } from "@/components/opportunity-detail";
import { demoRequest } from "@/lib/demo-client";
import { FIELD_LABELS, STATUS_LABELS, profileHref, type CriterionAssessment, type Recommendation } from "@/lib/recommendations";

const groups: { status: CriterionAssessment["status"]; title: string; color: string }[] = [
  { status: "met", title: "Requirements that appear satisfied", color: "border-emerald-200 bg-emerald-50" },
  { status: "not_met", title: "Requirements that appear unsatisfied", color: "border-rose-200 bg-rose-50" },
  { status: "unknown", title: "Requirements needing more information", color: "border-amber-200 bg-amber-50" },
];

export function RecommendationDetail({ id }: { id: string }) {
  const [item, setItem] = useState<Recommendation | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { demoRequest<Recommendation>(`recommendations/${id}`).then(setItem).catch(cause => setError(cause instanceof Error ? cause.message : "Could not load this recommendation")); }, [id]);
  return <div className="min-h-screen bg-[#f6f8f5] text-slate-900">
    <header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-4 sm:px-8"><Link href="/explore" className="flex items-center gap-2 text-xl font-bold"><span className="grid size-9 place-items-center rounded-xl bg-emerald-800 text-white"><Leaf size={20}/></span>Seedline<span className="text-emerald-700">.</span></Link><nav className="flex gap-5 text-sm font-semibold"><Link href="/recommendations" className="text-emerald-800">Recommendations</Link><Link href="/dashboard" className="text-slate-600">My profile</Link></nav></div></header>
    <main className="mx-auto max-w-6xl px-5 pb-20 pt-9 sm:px-8"><Link href="/recommendations" className="inline-flex items-center gap-1 text-sm font-semibold text-emerald-800 hover:underline"><ArrowLeft size={15}/>All recommendations</Link>
      {error && <p role="alert" className="mt-7 rounded-xl bg-rose-50 p-5 text-sm text-rose-800">{error} <Link href="/demo" className="ml-2 font-bold underline">Start a demo profile</Link></p>}
      {!item && !error && <p className="mt-8 text-sm text-slate-500">Assessing this opportunity…</p>}
      {item && <><div className="mb-7 mt-8"><p className="text-xs font-bold uppercase tracking-widest text-emerald-700">Personalized opportunity assessment</p><h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">{item.opportunity.title}</h1><div className="mt-4 flex flex-wrap gap-2"><span className="rounded-full bg-white px-3 py-1.5 text-xs font-bold text-emerald-900">{item.relevance_score === null ? "Complete profile for relevance" : `${item.relevance_score}/100 relevance`}</span><span className="rounded-full bg-white px-3 py-1.5 text-xs font-bold text-slate-800">{STATUS_LABELS[item.eligibility_status]}</span></div></div>
        <section className="mb-7 rounded-[1.5rem] border border-emerald-200 bg-white p-6 shadow-sm sm:p-8"><h2 className="text-2xl font-semibold">How This Opportunity Matches Your Business</h2><p className="mt-3 text-sm leading-6 text-slate-600">{item.explanation} A relevance score is a ranking signal, separate from eligibility. Confirm every requirement with the funder before applying.</p>
          {item.relevance_score !== null && <div className="mt-5 flex flex-wrap gap-2">{Object.entries(item.score_breakdown).map(([name, points]) => <span key={name} className={`rounded-full px-3 py-1 text-xs font-semibold ${points ? "bg-emerald-50 text-emerald-800" : "bg-slate-50 text-slate-500"}`}>{name.replaceAll("_", " ")}: {points} points</span>)}</div>}
          <div className="mt-7 grid gap-4 lg:grid-cols-3">{groups.map(group => { const checks = item.criteria.filter(check => check.status === group.status); return <div key={group.status} className={`rounded-xl border p-4 ${group.color}`}><h3 className="font-semibold">{group.title}</h3>{checks.length ? <ul className="mt-3 space-y-4">{checks.map((check, index) => <li key={`${check.source_rule_id ?? check.label}-${index}`} className="text-sm leading-6"><p className="font-semibold">{check.label}</p><p className="mt-1 text-slate-700">{check.requirement}</p><p className="mt-1 text-slate-600">{check.explanation}</p>{check.unknown_reason === "opportunity_data_missing" && <p className="mt-1 text-amber-900">This criterion is missing from the funding record.</p>}{check.unknown_reason === "unsupported_rule" && <p className="mt-1 text-amber-900">This sourced condition needs manual review.</p>}{check.source_url && <a href={check.source_url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-block font-semibold text-emerald-800 hover:underline">Original requirement ↗</a>}{check.status === "unknown" && check.unknown_reason === "profile_missing" && check.field && <Link href={profileHref(check.field, `/recommendations/${id}`)} className="ml-3 inline-block font-semibold text-emerald-800 hover:underline">Update {FIELD_LABELS[check.field] ?? check.field.replaceAll("_", " ")} →</Link>}</li>)}</ul> : <p className="mt-3 text-sm text-slate-600">None recorded.</p>}</div>; })}</div>
          {item.missing_profile_fields.length > 0 && <div className="mt-6 rounded-xl bg-amber-50 p-4 text-sm text-amber-950"><CircleHelp size={17} className="mr-2 inline"/>We found potentially relevant funding, but need {item.missing_profile_fields.map(field => FIELD_LABELS[field] ?? field.replaceAll("_", " ")).join(", ").toLowerCase()} to assess these requirements. <Link href={profileHref(item.missing_profile_fields[0], `/recommendations/${id}`)} className="font-bold underline">Update profile</Link><Link href={`/assistant?opportunity=${id}`} className="ml-4 font-bold underline">Check eligibility with Seedline →</Link></div>}
        </section><OpportunityDetail item={item.opportunity}/></>}
    </main>
  </div>;
}
