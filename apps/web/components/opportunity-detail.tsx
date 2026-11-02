import { CheckCircle2, CircleHelp, ExternalLink, MapPin } from "lucide-react";
import { applicantLabel, formatDeadline, publicSummary, type Opportunity } from "@/lib/api";
import { fundingAmount } from "@/lib/recommendations";

function date(value: string | null) { return value ? new Date(value).toLocaleDateString("en-CA", { year: "numeric", month: "long", day: "numeric" }) : "Unconfirmed"; }

export function OpportunityDetail({ item, admin = false }: { item: Opportunity; admin?: boolean }) {
  const summary = publicSummary(item.summary, admin);
  return <div className="space-y-6">
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
      <Fact label="Funding type" value={item.funding_type} />
      <Fact label="Funding amount" value={item.amount_min !== null || item.amount_max !== null ? fundingAmount(item) : null} />
      <Fact label="Geography" value={item.geography} />
      <Fact label="Applicants" value={applicantLabel(item)} />
      <Fact label="Application status" value={item.application_status === "unknown" ? null : item.application_status} />
    </div>
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h2 className="text-lg font-semibold text-slate-900">About this funding</h2><p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-600">{summary || "A verified description is not available yet."}</p><div className="mt-5 flex flex-wrap gap-3 text-sm text-slate-600"><span className="inline-flex items-center gap-1"><MapPin size={16} aria-hidden="true" />{item.geography || "Location unconfirmed"}</span>{item.url && <a href={item.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold text-teal-800 hover:underline">Official source <ExternalLink size={15} aria-hidden="true" /></a>}</div></section>
    {item.details && Object.keys(item.details).length > 0 && <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h2 className="text-lg font-semibold text-slate-900">Program details</h2><dl className="mt-4 grid gap-4 sm:grid-cols-2">{Object.entries(item.details).map(([key, value]) => <div key={key}><dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">{key.replaceAll("_", " ")}</dt><dd className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{Array.isArray(value) ? value.join(" · ") : String(value)}</dd></div>)}</dl></section>}
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h2 className="text-lg font-semibold text-slate-900">Application rounds</h2>{item.rounds.length ? <div className="mt-4 space-y-3">{item.rounds.map(round => <div key={round.id} className="rounded-xl bg-slate-50 p-4"><div className="flex justify-between gap-3"><h3 className="font-medium text-slate-900">{round.name}</h3><span className="text-xs font-semibold capitalize text-teal-800">{round.status === "unknown" ? "Intake unconfirmed" : round.status}</span></div><p className="mt-2 text-sm text-slate-600">{round.opens_at ? `Opens: ${formatDeadline(round.opens_at)}. ` : null}Deadline: {formatDeadline(round.deadline)}</p>{round.application_url && <a href={round.application_url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-block text-sm font-medium text-teal-800 hover:underline">Application page ↗</a>}</div>)}</div> : <Unknown text="No application round has been confirmed." />}</section>
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h2 className="text-lg font-semibold text-slate-900">Eligibility requirements</h2>{item.eligibility_rules.length ? <div className="mt-4 space-y-4">{item.eligibility_rules.map(rule => <div key={rule.id} className="border-l-2 border-teal-300 pl-4"><h3 className="text-sm font-semibold capitalize text-slate-900">{rule.criterion}</h3><p className="mt-1 text-sm leading-6 text-slate-600">{rule.requirement}</p>{rule.source_url && <a href={rule.source_url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-block text-xs font-medium text-teal-800 hover:underline">Requirement source ↗</a>}</div>)}</div> : <Unknown text="Eligibility details have not been confirmed. Check the official source before applying." />}</section>
    </div>
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"><h2 className="text-lg font-semibold text-slate-900">Record status</h2><div className="mt-4 grid gap-4 text-sm sm:grid-cols-3"><Fact label="Verified" value={item.verified_at ? date(item.verified_at) : null} /><Fact label="Published" value={item.published_at ? date(item.published_at) : null} /><Fact label="Last updated" value={date(item.updated_at)} /></div>{admin && <p className="mt-4 text-xs text-slate-500">Verification: {item.verification_status}. Publication: {item.publication_status}. Edits require a new review.</p>}</section>
  </div>;
}

function Fact({ label, value }: { label: string; value: string | null }) { return <div className="rounded-xl bg-slate-50 p-4"><div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div><div className="mt-2 flex items-center gap-1 text-sm font-semibold capitalize text-slate-900">{value ? <CheckCircle2 size={15} className="text-teal-700" aria-hidden="true" /> : <CircleHelp size={15} className="text-amber-600" aria-hidden="true" />}{value || "Unconfirmed"}</div></div>; }
function Unknown({ text }: { text: string }) { return <p className="mt-4 rounded-xl bg-amber-50 p-4 text-sm leading-6 text-amber-900">{text}</p>; }
