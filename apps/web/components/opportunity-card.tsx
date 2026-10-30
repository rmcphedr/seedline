import Link from "next/link";
import { ArrowUpRight, CalendarDays, MapPin } from "lucide-react";
import { formatDeadline, publicSummary, type Opportunity } from "@/lib/api";

const typeLabels: Record<string, string> = {
  grant: "Grant", loan: "Loan", investment: "Investment", procurement: "Procurement", competition: "Competition",
};

export function OpportunityCard({ item, href, admin = false }: { item: Opportunity; href: string; admin?: boolean }) {
  const deadline = item.rounds.find(round => round.status === "open" && round.deadline)?.deadline;
  return <Link href={href} className="group block rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition hover:-translate-y-0.5 hover:border-teal-300 hover:shadow-md">
    <div className="flex items-start justify-between gap-4">
      <div className="flex flex-wrap gap-2 text-xs font-semibold">
        <span className="rounded-full bg-teal-50 px-3 py-1 text-teal-800">{typeLabels[item.funding_type] ?? item.funding_type}</span>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-700">{item.application_status === "unknown" ? "Intake unconfirmed" : `${item.application_status} intake`}</span>
        {admin && <span className="rounded-full bg-amber-50 px-3 py-1 text-amber-800">{item.verification_status} · {item.publication_status}</span>}
      </div>
      <ArrowUpRight size={19} className="shrink-0 text-slate-400 transition group-hover:text-teal-700" aria-hidden="true" />
    </div>
    <h2 className="mt-5 text-xl font-semibold tracking-tight text-slate-900 group-hover:text-teal-800">{item.title}</h2>
    <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-600">{publicSummary(item.summary, admin) || "A description has not been confirmed yet."}</p>
    <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-slate-100 pt-4 text-xs text-slate-500">
      <span className="inline-flex items-center gap-1"><MapPin size={14} aria-hidden="true" />{item.geography || "Location unconfirmed"}</span>
      <span>{item.organization_types.length ? item.organization_types.join(" · ") : "Applicant types unconfirmed"}</span>
      {deadline && <span className="inline-flex items-center gap-1"><CalendarDays size={14} aria-hidden="true" />Deadline {formatDeadline(deadline)}</span>}
    </div>
  </Link>;
}
