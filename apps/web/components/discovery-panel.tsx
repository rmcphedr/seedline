import Link from "next/link";
import { ArrowUpRight, SearchCheck } from "lucide-react";
import { decideCandidate } from "@/app/actions";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import type { Candidate, Source } from "@/lib/api";

export function DiscoveryPanel({ candidates, sources }: { candidates: Candidate[]; sources: Source[] }) {
  return <div className="space-y-4">
    <Card><CardContent className="flex items-start gap-3 text-sm text-slate-600"><SearchCheck size={20} className="mt-0.5 shrink-0 text-indigo-600"/><p>These are unverified URLs from discovery. Check the official page before promoting a candidate; promotion creates a pending funding program for final review.</p></CardContent></Card>
    {candidates.map(candidate => <Card key={candidate.id}><CardContent className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div><div className="flex flex-wrap items-center gap-2"><h2 className="text-lg font-semibold text-slate-900">{candidate.title || "Untitled candidate"}</h2><Badge>{candidate.extracted_data?.type_hint || "unknown type"}</Badge></div>
        <a href={candidate.canonical_url || candidate.url} target="_blank" rel="noreferrer" className="mt-2 inline-flex break-all text-sm text-indigo-600 hover:underline">{candidate.canonical_url || candidate.url}<ArrowUpRight size={15} className="ml-1 shrink-0"/></a>
        <p className="mt-3 text-sm leading-6 text-slate-600">{candidate.extracted_data?.reason_to_investigate || "No research note supplied."}</p>
        <div className="mt-3 text-xs text-slate-500">Source: {sources.find(source => source.id === candidate.source_id)?.name || "Unregistered source"} · Status: {candidate.status}</div>
      </div>
      <form action={decideCandidate} className="space-y-3"><input type="hidden" name="id" value={candidate.id}/><label className="block text-sm font-medium text-slate-700">Verified funding type<select name="funding_type" required className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm"><option value="">Choose after checking source</option>{["grant", "loan", "investment", "procurement", "competition"].map(type => <option key={type} value={type}>{type}</option>)}</select></label><div className="flex gap-2"><Button name="decision" value="promote" className="flex-1">Send to review</Button><Button name="decision" value="dismiss" variant="outline" className="flex-1" formNoValidate>Dismiss</Button></div></form>
    </CardContent></Card>)}
    {candidates.length === 0 && <div className="rounded-xl border border-dashed border-slate-200 bg-white px-6 py-12 text-center text-sm text-slate-500">No unverified candidates yet. Run a search from <Link href="/admin/discovery" className="text-indigo-600 underline">admin discovery</Link>.</div>}
  </div>;
}
