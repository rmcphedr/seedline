import Link from "next/link";
import { ArrowRight, CheckCircle2, CircleDollarSign, Database, FileCheck2, Layers3, Plus, Search, ShieldCheck, SearchCheck } from "lucide-react";
import { api, type Candidate, type Job, type Opportunity, type Review, type Source, type UsageEvent, type UsageSummary } from "@/lib/api";
import { DiscoveryPanel } from "@/components/discovery-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createJob, createOpportunity, createSource, decideReview, deleteSource, toggleSource } from "./actions";

export const dynamic = "force-dynamic";
type Params = { view?: string; search?: string; funding_type?: string; review_status?: string; message?: string };
const sections = [
  { id: "opportunities", label: "Opportunities", icon: CircleDollarSign },
  { id: "sources", label: "Sources", icon: Database },
  { id: "ingestion", label: "Ingestion", icon: Layers3 },
  { id: "discovery", label: "Discovery", icon: SearchCheck },
  { id: "review", label: "Review Queue", icon: FileCheck2 }
];
const selectClass = "h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500";
function date(value?: string | null) { return value ? new Date(value).toLocaleDateString("en-CA", { year: "numeric", month: "short", day: "numeric" }) : "—"; }
function statusClass(status: string) { return status === "approved" || status === "open" || status === "succeeded" ? "bg-emerald-50 text-emerald-700" : status === "rejected" || status === "failed" ? "bg-rose-50 text-rose-700" : "bg-amber-50 text-amber-700"; }
function Status({ value }: { value: string }) { return <Badge className={statusClass(value)}>{value}</Badge>; }
function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="block space-y-1.5 text-sm font-medium text-slate-700"><span>{label}</span>{children}</label>; }
function Empty({ text }: { text: string }) { return <div className="rounded-xl border border-dashed border-slate-200 bg-white px-6 py-12 text-center text-sm text-slate-500">{text}</div>; }

export default async function Dashboard({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams;
  const view = sections.some(section => section.id === params.view) ? params.view! : "opportunities";
  let sources: Source[] = [], opportunities: Opportunity[] = [], jobs: Job[] = [], reviews: Review[] = [], candidates: Candidate[] = [];
  let usage: UsageSummary | null = null;
  let usageEvents: UsageEvent[] = [];
  let error: string | null = null;
  try {
    const query = new URLSearchParams();
    if (params.search) query.set("search", params.search);
    if (params.funding_type) query.set("funding_type", params.funding_type);
    if (params.review_status) query.set("review_status", params.review_status);
    [sources, opportunities, jobs, reviews, candidates, usage, usageEvents] = await Promise.all([
      api<Source[]>("/sources"), api<Opportunity[]>(`/opportunities?${query}`), api<Job[]>("/ingestion-jobs"),
      api<Review[]>("/review-queue"), api<Candidate[]>("/candidates?status=unverified"),
      api<UsageSummary>("/discovery/usage-summary"), api<UsageEvent[]>("/discovery/usage")
    ]);
  } catch (cause) { error = cause instanceof Error ? cause.message : "Could not reach the API"; }
  const title = sections.find(section => section.id === view)!.label;

  return <div className="min-h-screen lg:flex">
    <aside className="border-b border-slate-200 bg-white lg:sticky lg:top-0 lg:h-screen lg:w-64 lg:shrink-0 lg:border-b-0 lg:border-r">
      <div className="flex items-center gap-3 border-b border-slate-100 px-6 py-6">
        <div className="flex size-10 items-center justify-center rounded-xl bg-indigo-600 text-white"><Layers3 size={21}/></div>
        <div><div className="text-xl font-bold tracking-tight">bridge<span className="text-indigo-600">.</span></div><div className="text-[11px] font-medium uppercase tracking-[0.19em] text-slate-400">Funding intelligence</div></div>
      </div>
      <nav className="flex gap-1 overflow-x-auto p-3 lg:block lg:space-y-1" aria-label="Dashboard sections">
        {sections.map(section => <Link key={section.id} href={`/?view=${section.id}`} className={`flex shrink-0 items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${view === section.id ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-50"}`}><section.icon size={18}/>{section.label}{section.id === "review" && reviews.length > 0 && <span className="ml-auto rounded-full bg-indigo-100 px-2 text-xs text-indigo-700">{reviews.length}</span>}{section.id === "discovery" && candidates.length > 0 && <span className="ml-auto rounded-full bg-indigo-100 px-2 text-xs text-indigo-700">{candidates.length}</span>}</Link>)}
        <Link href="/admin/opportunities" className="flex shrink-0 items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-teal-800 hover:bg-teal-50"><ShieldCheck size={18}/>Opportunity admin</Link>
        <Link href="/explore" className="flex shrink-0 items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-teal-800 hover:bg-teal-50"><SearchCheck size={18}/>Public explorer</Link>
      </nav>
      <div className="hidden px-6 pt-8 text-xs leading-5 text-slate-400 lg:block"><ShieldCheck className="mb-2 text-indigo-500" size={18}/>Human review keeps published funding information trustworthy.</div>
    </aside>

    <main className="mx-auto w-full max-w-7xl px-5 py-7 sm:px-8 lg:px-10 lg:py-10">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4"><div><div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-indigo-600">Operations workspace</div><h1 className="text-3xl font-semibold tracking-tight text-slate-900">{title}</h1><p className="mt-2 text-sm text-slate-500">Manage the information that connects organizations to funding.</p></div><div className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-500">Bridge admin · Discovery preview</div></div>
      {error && <div role="alert" className="mb-6 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">API unavailable: {error}. Start the database and API, then refresh.</div>}
      {params.message && <div role="status" className="mb-6 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800"><CheckCircle2 size={17}/>{params.message}</div>}
      <div className="mb-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Funding opportunities" value={opportunities.length} detail="In the current view" />
        <Metric label="Active sources" value={sources.filter(source => source.active).length} detail="Registered and enabled" />
        <Metric label="Awaiting review" value={reviews.length} detail="Needs a human decision" />
        <Metric label="Discovery candidates" value={candidates.length} detail="Unverified URLs" />
      </div>
      {view === "opportunities" && <Opportunities items={opportunities} sources={sources} params={params}/>}
      {view === "sources" && <Sources items={sources}/>}
      {view === "ingestion" && <Ingestion items={jobs} sources={sources} usage={usage} usageEvents={usageEvents}/>}
      {view === "discovery" && <DiscoveryPanel candidates={candidates} sources={sources}/>}
      {view === "review" && <Reviews items={reviews}/>}
    </main>
  </div>;
}

function Metric({ label, value, detail }: { label: string; value: number; detail: string }) { return <Card><CardContent className="p-5"><div className="text-sm font-medium text-slate-500">{label}</div><div className="mt-2 text-3xl font-semibold text-slate-900">{value}</div><div className="mt-1 text-xs text-slate-400">{detail}</div></CardContent></Card>; }

function Opportunities({ items, sources, params }: { items: Opportunity[]; sources: Source[]; params: Params }) { return <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
  <div className="space-y-5"><Card><CardHeader><form className="flex flex-wrap gap-2"><input type="hidden" name="view" value="opportunities"/><div className="relative min-w-48 flex-1"><Search size={16} className="absolute left-3 top-3 text-slate-400"/><Input name="search" defaultValue={params.search} placeholder="Search opportunities" className="pl-9"/></div><select aria-label="Funding type" name="funding_type" defaultValue={params.funding_type ?? ""} className={selectClass}><option value="">All types</option>{["grant", "loan", "investment", "procurement", "competition"].map(x => <option key={x} value={x}>{x}</option>)}</select><select aria-label="Review status" name="review_status" defaultValue={params.review_status ?? ""} className={selectClass}><option value="">All statuses</option>{["pending", "approved", "rejected"].map(x => <option key={x} value={x}>{x}</option>)}</select><Button type="submit" variant="outline">Filter</Button></form></CardHeader><div className="divide-y divide-slate-100">{items.map(item => <Link href={`/admin/opportunities/${item.id}`} key={item.id} className="flex items-start justify-between gap-4 px-5 py-4 transition-colors hover:bg-slate-50"><div><div className="font-semibold text-slate-900">{item.title}</div><div className="mt-1 line-clamp-2 text-sm text-slate-500">{item.summary || "No summary yet"}</div><div className="mt-3 flex flex-wrap items-center gap-2"><Badge>{item.funding_type}</Badge><Status value={item.review_status}/>{item.rounds[0]?.deadline && <span className="text-xs text-slate-400">Deadline {date(item.rounds[0].deadline)}</span>}</div></div><ArrowRight size={17} className="mt-1 shrink-0 text-slate-400"/></Link>)}</div></Card>{items.length === 0 && <Empty text="No opportunities match this view. Add one to start the funding catalog."/>}</div>
  <Card className="h-fit"><CardHeader><div className="flex items-center gap-2 font-semibold"><Plus size={17} className="text-indigo-600"/>Add opportunity</div><p className="mt-1 text-xs text-slate-500">New records go to the review queue.</p></CardHeader><CardContent><form action={createOpportunity} className="space-y-4"><Field label="Title"><Input name="title" required placeholder="e.g. Growth Grant"/></Field><Field label="Funding type"><select name="funding_type" className={`${selectClass} w-full`}>{["grant", "loan", "investment", "procurement", "competition"].map(x => <option key={x} value={x}>{x}</option>)}</select></Field><Field label="Source"><select name="source_id" className={`${selectClass} w-full`}><option value="">No registered source</option>{sources.map(source => <option key={source.id} value={source.id}>{source.name}</option>)}</select></Field><Field label="Official URL"><Input name="url" type="url" placeholder="https://..."/></Field><Field label="Geography"><Input name="geography" placeholder="e.g. Canada"/></Field><Field label="Deadline"><Input name="deadline" type="date"/></Field><Field label="Summary"><textarea name="summary" rows={3} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Brief description"/></Field><Button className="w-full" type="submit">Submit for review</Button></form></CardContent></Card>
</div>; }

function Sources({ items }: { items: Source[] }) { return <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]"><div className="space-y-4">{items.map(source => <Card key={source.id}><CardContent className="flex flex-wrap items-center justify-between gap-4"><div><div className="font-semibold text-slate-900">{source.name}</div><a href={source.base_url} target="_blank" rel="noreferrer" className="mt-1 block break-all text-sm text-indigo-600 hover:underline">{source.base_url}</a><div className="mt-3 flex gap-2"><Badge>{source.kind}</Badge><Status value={source.active ? "active" : "inactive"}/></div></div><div className="flex gap-2"><form action={toggleSource}><input type="hidden" name="id" value={source.id}/><input type="hidden" name="active" value={String(!source.active)}/><Button variant="outline" size="sm">{source.active ? "Disable" : "Enable"}</Button></form><form action={deleteSource}><input type="hidden" name="id" value={source.id}/><Button variant="ghost" size="sm">Delete</Button></form></div></CardContent></Card>)}{items.length === 0 && <Empty text="No funding sources registered yet."/>}</div><Card className="h-fit"><CardHeader><div className="flex items-center gap-2 font-semibold"><Plus size={17} className="text-indigo-600"/>Register source</div></CardHeader><CardContent><form action={createSource} className="space-y-4"><Field label="Source name"><Input name="name" required placeholder="Funding organization"/></Field><Field label="Website or API URL"><Input name="base_url" type="url" required placeholder="https://..."/></Field><Field label="Source type"><select name="kind" className={`${selectClass} w-full`}><option value="website">Website</option><option value="api">API</option><option value="directory">Directory</option></select></Field><Button className="w-full">Add source</Button></form></CardContent></Card></div>; }

function Ingestion({ items, sources, usage, usageEvents }: { items: Job[]; sources: Source[]; usage: UsageSummary | null; usageEvents: UsageEvent[] }) {
  return <div className="space-y-6">
    {usage && <Card><CardHeader><div className="font-semibold">Discovery usage this month</div><p className="mt-1 text-xs text-slate-500">Recorded provider responses. Estimates use your configured rate card and are not billing invoices.</p></CardHeader><CardContent className="grid gap-4 sm:grid-cols-4"><div><div className="text-xs text-slate-500">Responses</div><div className="mt-1 text-xl font-semibold">{usage.response_count}</div></div><div><div className="text-xs text-slate-500">Input / output tokens</div><div className="mt-1 text-xl font-semibold">{usage.input_tokens.toLocaleString()} / {usage.output_tokens.toLocaleString()}</div></div><div><div className="text-xs text-slate-500">Web searches</div><div className="mt-1 text-xl font-semibold">{usage.web_search_calls}</div></div><div><div className="text-xs text-slate-500">Estimated USD</div><div className="mt-1 text-xl font-semibold">{usage.estimated_cost_usd === null ? "—" : `$${usage.estimated_cost_usd.toFixed(4)}`}</div><div className="text-xs text-slate-400">{usage.estimated_cost_usd === null ? "Configure rates to estimate" : "Based on saved rate snapshots"}</div></div></CardContent></Card>}
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]"><div className="space-y-4">{items.map(job => {
      const events = usageEvents.filter(event => event.job_id === job.id);
      const tokens = events.reduce((total, event) => total + event.input_tokens + event.output_tokens, 0);
      const searches = events.reduce((total, event) => total + event.web_search_calls, 0);
      const jobCost = events.length > 0 && events.every(event => event.estimated_cost_usd !== null)
        ? events.reduce((total, event) => total + (event.estimated_cost_usd ?? 0), 0) : null;
      return <Card key={job.id}><CardContent className="flex items-center justify-between gap-4"><div>
        <div className="font-semibold text-slate-900">{job.job_metadata?.kind === "csv_seed_import" ? "CSV funding seed import" : sources.find(source => source.id === job.source_id)?.name ?? (job.job_metadata?.mode === "open" ? "Open-web discovery" : "Unknown source")}</div>
        <div className="mt-1 text-sm text-slate-600">{job.job_metadata?.kind === "csv_seed_import" ? `${job.job_metadata.file}: ${job.job_metadata.programs_created} programs, ${job.job_metadata.candidates_created} candidates, ${job.job_metadata.source_only_rows} source listings` : job.job_metadata?.query || "No discovery query"}</div>
        <div className="mt-2 text-xs text-slate-500">Created {date(job.created_at)} · {job.id.slice(0, 8)}</div>
        {events.length > 0 && <div className="mt-2 text-xs text-slate-500">{events.length} responses · {tokens.toLocaleString()} tokens · {searches} web searches · {jobCost === null ? "Cost estimate unavailable" : `$${jobCost.toFixed(4)} estimated`}</div>}
        {job.error && <p className="mt-2 text-sm text-rose-600">{job.error}</p>}
      </div><Status value={job.status}/></CardContent></Card>;
    })}{items.length === 0 && <Empty text="No ingestion jobs recorded yet."/>}</div>
    <Card className="h-fit"><CardHeader><div className="font-semibold">Queue discovery job</div><p className="mt-1 text-xs text-slate-500">Queueing makes no model calls. Running a job requires a separate explicit CLI command.</p></CardHeader><CardContent><form action={createJob} className="space-y-4"><Field label="Mode"><select name="mode" className={`${selectClass} w-full`}><option value="trusted">Trusted source</option><option value="open">Open web</option></select></Field><Field label="Funding source (required for trusted mode)"><select name="source_id" className={`${selectClass} w-full`}><option value="">Choose a source</option>{sources.map(source => <option key={source.id} value={source.id}>{source.name}</option>)}</select></Field><Field label="Research objective"><textarea name="query" required rows={3} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" placeholder="Find funding for women-led nonprofits in Canada"/></Field><Field label="Maximum candidates"><Input name="limit" type="number" min="1" max="30" defaultValue="8" required/></Field><Button className="w-full">Create queued job</Button></form></CardContent></Card></div>
  </div>;
}

function Reviews({ items }: { items: Review[] }) { return <div className="space-y-4">{items.map(review => <Card key={review.id}><CardContent className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]"><div><div className="flex flex-wrap items-center gap-2"><h2 className="text-lg font-semibold text-slate-900">{review.program.title}</h2><Badge>{review.program.funding_type}</Badge></div><p className="mt-2 text-sm leading-6 text-slate-600">{review.program.summary || "No summary supplied."}</p><div className="mt-4 flex flex-wrap gap-3 text-xs text-slate-500"><span>{review.program.geography || "Geography unspecified"}</span><span>·</span><span>{review.program.rounds.length} application rounds</span><span>·</span><span>{review.program.eligibility_rules.length} eligibility rules</span></div><Link href={`/admin/opportunities/${review.program.id}`} className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-indigo-600 hover:underline">Inspect record <ArrowRight size={14}/></Link></div><form action={decideReview} className="space-y-3"><input type="hidden" name="id" value={review.id}/><Field label="Decision note"><Input name="note" placeholder="Optional verification note"/></Field><div className="flex gap-2"><Button name="decision" value="approve" className="flex-1">Approve</Button><Button name="decision" value="reject" variant="outline" className="flex-1">Reject</Button></div></form></CardContent></Card>)}{items.length === 0 && <Empty text="The review queue is clear. Newly submitted opportunities will appear here."/>}</div>; }
