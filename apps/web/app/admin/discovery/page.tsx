import Link from "next/link";
import { Search } from "lucide-react";
import { DiscoverySubmit } from "@/components/discovery-submit";
import { api, type Candidate, type Job, type Source } from "@/lib/api";
import { decideAdminCandidate, runAdminDiscovery } from "../actions";

export const dynamic = "force-dynamic";

type Params = { message?: string; job?: string };
const input = "w-full rounded-lg border border-slate-200 bg-white px-3 text-sm focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100";

export default async function AdminDiscovery({ searchParams }: { searchParams: Promise<Params> }) {
  const params = await searchParams;
  const [jobs, candidates, sources] = await Promise.all([
    api<Job[]>("/ingestion-jobs"),
    api<Candidate[]>("/candidates?status=unverified&limit=50"),
    api<Source[]>("/sources"),
  ]);
  const runs = jobs.filter(job => job.job_metadata?.kind === "query_discovery");
  const focus = runs.find(job => job.id === params.job);
  const leads = focus ? candidates.filter(candidate => candidate.job_id === focus.id) : candidates;
  const activeSources = sources.filter(source => source.active);

  return (
    <main className="mx-auto max-w-7xl px-5 py-9 sm:px-8">
      <div className="mb-8">
        <p className="text-xs font-semibold uppercase tracking-widest text-teal-700">Administration</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">Discovery</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Ask for more opportunities in plain language. The search uses pages already on file so it does not save the same source or program again.
        </p>
      </div>
      {params.message && <p role="status" className="mb-5 rounded-xl bg-teal-50 px-4 py-3 text-sm text-teal-900">{params.message}</p>}
      <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_340px]">
        <section className="space-y-8">
          <div>
            <div className="mb-4 flex items-baseline justify-between gap-3">
              <h2 className="text-lg font-semibold text-slate-900">{focus ? "Leads from this search" : "Unverified leads"}</h2>
              <span className="text-sm text-slate-500">{leads.length} shown</span>
            </div>
            <div className="space-y-4">
              {leads.map(candidate => <Lead key={candidate.id} candidate={candidate} sources={sources} />)}
              {leads.length === 0 && (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">
                  {focus?.status === "failed"
                    ? "This search did not finish. The note above explains why."
                    : "No new leads yet. Run a search, then send a useful page to review."}
                </div>
              )}
            </div>
          </div>
          {focus && <Skipped job={focus} />}
          <div>
            <h2 className="mb-4 text-lg font-semibold text-slate-900">Recent searches</h2>
            <div className="space-y-3">
              {runs.slice(0, 8).map(job => <Run key={job.id} job={job} active={job.id === focus?.id} />)}
              {runs.length === 0 && <p className="text-sm text-slate-500">No discovery searches yet.</p>}
            </div>
          </div>
        </section>
        <aside className="h-fit rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2">
            <Search size={18} className="text-teal-800" aria-hidden="true" />
            <h2 className="font-semibold text-slate-900">Find opportunities</h2>
          </div>
          <p className="mt-2 text-xs leading-5 text-slate-500">
            Example: find 5 more opportunities in Canada that are women-focused. Each result needs a link to the opportunity page. New leads stay unverified.
          </p>
          <form action={runAdminDiscovery} className="mt-5 space-y-4">
            <label className="block text-xs font-semibold text-slate-600">
              What should we look for?
              <textarea name="query" required rows={4} className={`${input} mt-1 py-2`} placeholder="find 5 more opportunities in Canada that are women-focused" />
            </label>
            <label className="block text-xs font-semibold text-slate-600">
              How many new leads
              <input className={`${input} mt-1 h-10`} name="limit" type="number" min={1} max={30} placeholder="Use the number in the query, or 5" />
            </label>
            <label className="block text-xs font-semibold text-slate-600">
              Registered source
              <select className={`${input} mt-1 h-10`} name="source_id" defaultValue="">
                <option value="">Open web</option>
                {activeSources.map(source => <option key={source.id} value={source.id}>{source.name}</option>)}
              </select>
            </label>
            <DiscoverySubmit />
          </form>
        </aside>
      </div>
    </main>
  );
}

function Lead({ candidate, sources }: { candidate: Candidate; sources: Source[] }) {
  const data = candidate.extracted_data;
  const href = candidate.canonical_url || candidate.url;
  const source = sources.find(item => item.id === candidate.source_id);
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold text-slate-900">{candidate.title || "Untitled lead"}</h3>
        <span className="rounded-full bg-teal-50 px-2.5 py-1 text-xs font-semibold text-teal-800">{data?.type_hint || "unknown type"}</span>
      </div>
      <a href={href} target="_blank" rel="noreferrer" className="mt-2 block break-all text-sm font-medium text-teal-800 hover:underline">{href}</a>
      {data?.summary && <p className="mt-3 text-sm leading-6 text-slate-700">{data.summary}</p>}
      <p className="mt-2 text-sm leading-6 text-slate-600">{data?.reason_to_investigate || "No search note supplied."}</p>
      <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
        <span>{data?.geography || "Geography not stated"}</span>
        <span>{data?.audience || "Audience not stated"}</span>
        <span>{source?.name || "Unregistered source"}</span>
      </div>
      <form action={decideAdminCandidate} className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end">
        <input type="hidden" name="id" value={candidate.id} />
        <label className="block flex-1 text-xs font-semibold text-slate-600">
          Funding type
          <select name="funding_type" required className={`${input} mt-1 h-10`}>
            <option value="">Choose after checking the page</option>
            {["grant", "loan", "investment", "procurement", "competition"].map(type => <option key={type} value={type}>{type}</option>)}
          </select>
        </label>
        <button name="decision" value="promote" className="h-10 rounded-lg bg-teal-800 px-4 text-sm font-semibold text-white hover:bg-teal-900">Send to review</button>
        <button name="decision" value="dismiss" formNoValidate className="h-10 rounded-lg border border-slate-200 px-4 text-sm font-semibold text-slate-700 hover:bg-slate-50">Dismiss</button>
      </form>
    </article>
  );
}

function Skipped({ job }: { job: Job }) {
  const skipped = job.job_metadata?.skipped ?? [];
  if (!skipped.length) return null;
  return (
    <div>
      <h2 className="mb-4 text-lg font-semibold text-slate-900">Already recorded</h2>
      <ul className="space-y-2">
        {skipped.map(item => (
          <li key={`${item.url}-${item.title}`} className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
            <span className="font-medium text-slate-900">{item.title || "Untitled"}</span>
            <span className="mt-1 block text-xs text-slate-500">{item.match === "title" ? "Same name as a saved opportunity" : "Same page as a saved record"}</span>
            {item.url && <a href={item.url} target="_blank" rel="noreferrer" className="mt-1 block break-all text-xs text-teal-800 hover:underline">{item.url}</a>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Run({ job, active }: { job: Job; active: boolean }) {
  const created = job.job_metadata?.candidates_created;
  const skipped = job.job_metadata?.duplicates_skipped;
  return (
    <Link href={`/admin/discovery?job=${job.id}`} className={`block rounded-2xl border bg-white p-4 shadow-sm ${active ? "border-teal-600" : "border-slate-200"}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{job.status}</span>
        <span className="text-xs text-slate-500">{new Date(job.created_at).toLocaleString("en-CA")}</span>
      </div>
      <p className="mt-2 text-sm text-slate-800">{job.job_metadata?.query}</p>
      {job.error && <p className="mt-2 text-sm text-rose-700">{job.error}</p>}
      {job.status === "succeeded" && <p className="mt-2 text-xs text-slate-500">{created ?? 0} new · {skipped ?? 0} already recorded · limit {job.job_metadata?.limit ?? "—"}</p>}
    </Link>
  );
}
