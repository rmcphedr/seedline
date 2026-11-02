import Link from "next/link";
import { ArrowRight, CalendarDays, CircleHelp, MapPin } from "lucide-react";
import { formatDeadline } from "@/lib/api";
import { FIELD_LABELS, STATUS_LABELS, fundingAmount, type Recommendation } from "@/lib/recommendations";

const statusColors = {
  likely_eligible: "bg-emerald-50 text-emerald-800",
  needs_information: "bg-amber-50 text-amber-800",
  potentially_ineligible: "bg-rose-50 text-rose-800",
};

export function RecommendationCard({ item }: { item: Recommendation }) {
  const opportunity = item.opportunity;
  const reasons = item.matched_criteria.slice(0, 3);
  return <article className="flex h-full flex-col rounded-[1.5rem] border border-slate-200 bg-white p-6 shadow-sm">
    <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-xs font-bold uppercase tracking-widest text-emerald-700">{opportunity.funding_type}</span><span className={`rounded-full px-3 py-1 text-xs font-bold ${statusColors[item.eligibility_status]}`}>{STATUS_LABELS[item.eligibility_status]}</span></div>
    <h3 className="mt-4 text-xl font-semibold leading-snug text-slate-950"><Link href={`/recommendations/${opportunity.id}`} className="hover:text-emerald-800">{opportunity.title}</Link></h3>
    <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm text-slate-600"><span>{fundingAmount(opportunity)}</span><span className="inline-flex items-center gap-1"><MapPin size={14}/>{opportunity.geography || "Location unconfirmed"}</span><span className="inline-flex items-center gap-1"><CalendarDays size={14}/>{item.deadline ? formatDeadline(item.deadline) : "Deadline unconfirmed"}</span></div>
    <div className="mt-5 rounded-xl bg-slate-50 p-4"><p className="text-sm font-semibold text-slate-900">{item.relevance_score === null ? "Profile needed for ranking" : `${item.relevance_score}/100 relevance`}</p><p className="mt-1 text-xs leading-5 text-slate-600">Relevance reflects industry, goals, stage, project, geography and funding type. It is separate from eligibility.</p></div>
    <p className="mt-4 text-sm leading-6 text-slate-600">{item.explanation}</p>
    {reasons.length > 0 && <div className="mt-4"><p className="text-xs font-bold uppercase tracking-wider text-slate-500">Known matches</p><ul className="mt-2 space-y-1 text-sm text-emerald-900">{reasons.map(reason => <li key={reason}>✓ {reason}</li>)}</ul></div>}
    {item.missing_profile_fields.length > 0 && <p className="mt-4 flex items-start gap-2 text-sm text-amber-900"><CircleHelp size={16} className="mt-0.5 shrink-0"/>Need your {item.missing_profile_fields.slice(0, 2).map(field => FIELD_LABELS[field] ?? field.replaceAll("_", " ")).join(" and ").toLowerCase()} to check eligibility.</p>}
    <Link href={`/recommendations/${opportunity.id}`} className="mt-auto inline-flex items-center gap-1 pt-6 text-sm font-bold text-emerald-800 hover:underline">See match details <ArrowRight size={15}/></Link>
  </article>;
}
