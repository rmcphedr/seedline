import Link from "next/link";
import { ArrowRight, Compass, SearchCheck } from "lucide-react";
import { OpportunityCard } from "@/components/opportunity-card";
import { OpportunityFilters, type FilterParams } from "@/components/opportunity-filters";
import { publicApi, type Opportunity } from "@/lib/api";
import { demoEnabled } from "@/lib/demo-server";

export const dynamic = "force-dynamic";

export default async function ExplorePage({ searchParams }: { searchParams: Promise<FilterParams & { page?: string }> }) {
  const params = await searchParams;
  const page = Math.max(1, Number.parseInt(params.page || "1", 10) || 1);
  const filterKeys = ["search", "funding_type", "geography", "organization_type", "application_status"] as const;
  const query = new URLSearchParams({ limit: "25", offset: String((page - 1) * 24) });
  for (const key of filterKeys) {
    if (params[key]) query.set(key, params[key]);
  }
  const results = await publicApi<Opportunity[]>(`/public/opportunities?${query}`);
  const opportunities = results.slice(0, 24);
  const demo = demoEnabled();
  const pageHref = (nextPage: number) => { const next = new URLSearchParams(); for (const key of filterKeys) if (params[key]) next.set(key, params[key]); next.set("page", String(nextPage)); return `/explore?${next}`; };
  return <div className="min-h-screen bg-[#f5f8f7]">
    <header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-5 sm:px-8"><Link href="/explore" className="flex items-center gap-2 text-xl font-bold tracking-tight text-slate-900"><span className="flex size-9 items-center justify-center rounded-xl bg-teal-800 text-white"><Compass size={21} aria-hidden="true" /></span>Seedline<span className="text-teal-700">.</span></Link><nav className="flex items-center gap-4 text-sm font-medium sm:gap-6"><Link href="/explore" className="text-teal-800">Explore funding</Link>{demo && <Link href="/recommendations" className="text-slate-600 hover:text-teal-800">For my business</Link>}{demo && <Link href="/dashboard" className="text-slate-600 hover:text-teal-800">My profile</Link>}<Link href="/admin/opportunities" className="text-slate-500 hover:text-slate-900">Admin</Link></nav></div></header>
    <main><section className="bg-gradient-to-br from-[#e7f3ef] via-white to-[#eef5f7]"><div className="mx-auto max-w-7xl px-5 py-14 sm:px-8 sm:py-20"><div className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-teal-800 shadow-sm"><SearchCheck size={15} aria-hidden="true" />Opportunity Explorer</div><h1 className="mt-5 max-w-3xl text-4xl font-semibold leading-tight tracking-tight text-slate-950 sm:text-5xl">Find funding that moves your work forward.</h1><p className="mt-5 max-w-2xl text-base leading-7 text-slate-600">Browse verified opportunities for entrepreneurs, small businesses, and nonprofits. Check each listing for intake and eligibility details before you apply.</p>{demo && <div className="mt-8 flex flex-wrap items-center gap-3"><Link href="/demo" className="inline-flex items-center gap-2 rounded-xl bg-emerald-800 px-5 py-3 text-sm font-semibold text-white shadow-sm hover:bg-emerald-900">Create Demo Profile<ArrowRight size={17}/></Link><span className="rounded-full bg-amber-50 px-3 py-2 text-xs font-bold uppercase tracking-wide text-amber-800">Local demo mode</span></div>}</div></section>
      <div className="mx-auto max-w-7xl px-5 py-10 sm:px-8"><OpportunityFilters params={params}/><div className="mt-9 flex items-end justify-between gap-4"><div><h2 className="text-2xl font-semibold tracking-tight text-slate-900">Available opportunities</h2><p className="mt-1 text-sm text-slate-500">Only verified, published records appear here.</p></div><span className="text-sm font-medium text-slate-500">{opportunities.length} result{opportunities.length === 1 ? "" : "s"}</span></div>
        {opportunities.length ? <div className="mt-6 grid gap-5 md:grid-cols-2 xl:grid-cols-3">{opportunities.map(item => <OpportunityCard key={item.id} item={item} href={`/explore/${item.id}`}/>)}</div> : <div className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center"><Compass size={30} className="mx-auto text-teal-700" aria-hidden="true" /><h3 className="mt-4 text-lg font-semibold text-slate-900">No published opportunities match yet</h3><p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-600">Try a broader filter. New resources appear here after an administrator verifies and publishes them.</p><Link href="/explore" className="mt-5 inline-flex items-center gap-1 text-sm font-semibold text-teal-800 hover:underline">Clear filters <ArrowRight size={15} aria-hidden="true" /></Link></div>}
        <div className="mt-6 flex gap-5 text-sm font-semibold text-teal-800">{page > 1 && <Link href={pageHref(page - 1)} className="hover:underline">← Previous</Link>}{results.length > 24 && <Link href={pageHref(page + 1)} className="hover:underline">Next →</Link>}</div>
      </div></main>
    <footer className="border-t border-slate-200 bg-white px-5 py-7 text-center text-xs text-slate-500">Seedline funding intelligence · Always confirm terms on the official source page.</footer>
  </div>;
}
