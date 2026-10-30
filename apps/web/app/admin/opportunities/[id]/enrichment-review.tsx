import type { EnrichmentJob } from "@/lib/api";
import { reviewEnrichment } from "../../actions";

const pretty = (value: unknown) => JSON.stringify(value, null, 2) ?? "null";

export function EnrichmentReview({ job, opportunityId }: { job: EnrichmentJob; opportunityId: string }) {
  const proposal = job.proposal;
  if (!proposal) return null;
  return <div className="mt-4 border-t border-slate-200 pt-4">
    <p className="text-xs text-slate-500">Source <a href={proposal.source_url} target="_blank" rel="noopener noreferrer" className="text-teal-800 underline">{proposal.source_url}</a> · SHA-256 {proposal.content_hash}</p>
    <p className="mt-2 text-xs text-slate-500">{proposal.extraction.model} · {proposal.extraction.tokens} tokens</p>
    {proposal.summary && <p className="mt-3 rounded-lg bg-teal-50 p-3 text-sm leading-6 text-slate-800">{proposal.summary}</p>}
    {proposal.missing.length > 0 && <p className="mt-2 text-xs text-amber-800">Still missing: {proposal.missing.join(", ")}</p>}
    {job.stage === "pending_review" ? <form action={reviewEnrichment} className="mt-4 space-y-4">
      <input type="hidden" name="id" value={opportunityId}/><input type="hidden" name="job_id" value={job.id}/>
      <p className="text-xs text-slate-600">Choose fields to apply. Edit the JSON value if needed. Conflicts and uncertainty require source review.</p>
      {Object.entries(proposal.proposed).map(([field, proposed]) => <div key={field} className="rounded-lg border border-slate-200 p-3">
        <label className="flex items-center gap-2 font-semibold"><input type="checkbox" name="accepted_fields" value={field} defaultChecked={!proposal.conflicts.includes(field) && !proposal.uncertain.includes(field)}/>{field.replaceAll("_", " ")}</label>
        <div className="mt-2 grid gap-2 sm:grid-cols-2"><div><p className="text-xs text-slate-500">Current</p><pre className="max-h-36 overflow-auto rounded bg-slate-50 p-2 text-xs">{pretty(proposal.existing[field])}</pre></div><div><p className="text-xs text-slate-500">Proposed JSON</p><textarea name={`field_${field}`} defaultValue={pretty(proposed)} rows={Math.min(7, Math.max(2, pretty(proposed).split("\n").length))} className="w-full rounded border border-slate-300 p-2 font-mono text-xs"/></div></div>
        {proposal.conflicts.includes(field) && <p className="mt-2 text-xs font-semibold text-amber-800">Conflicts with existing value</p>}
        {proposal.uncertain.includes(field) && <p className="mt-1 text-xs font-semibold text-rose-700">Evidence is missing or uncertain</p>}
        {proposal.evidence.filter(item => item.field === field).map((item, index) => <blockquote key={index} className="mt-2 border-l-2 border-teal-300 pl-2 text-xs text-slate-600">“{item.excerpt}”</blockquote>)}
      </div>)}
      <div className="flex gap-2"><button name="decision" value="approve" className="rounded-lg bg-teal-800 px-3 py-2 font-semibold text-white">Apply selected</button><button name="decision" value="reject" className="rounded-lg border border-rose-300 px-3 py-2 font-semibold text-rose-700">Reject proposal</button></div>
    </form> : <p className="mt-3 text-sm font-semibold">Review: {job.review_decision || job.stage}</p>}
  </div>;
}
