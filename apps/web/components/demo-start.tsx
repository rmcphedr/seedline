"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowRight, Leaf, Sparkles } from "lucide-react";
import { demoRequest } from "@/lib/demo-client";
import type { DemoContext } from "@/lib/demo-types";

export function DemoStart() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function create(example: boolean, assistant = false) {
    setBusy(true); setError("");
    try {
      await demoRequest<DemoContext>(example ? "example" : "create", "POST", example ? {} : { display_name: name.trim() || null });
      router.push(example ? "/dashboard" : assistant ? "/assistant" : "/onboarding");
      router.refresh();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not start the demo"); setBusy(false); }
  }
  return <main className="min-h-screen bg-[#f6f8f5] text-slate-900">
    <header className="mx-auto flex max-w-6xl items-center justify-between px-5 py-6 sm:px-8"><Link href="/explore" className="flex items-center gap-2 text-xl font-bold tracking-tight"><span className="grid size-9 place-items-center rounded-xl bg-emerald-800 text-white"><Leaf size={20}/></span>Seedline<span className="text-emerald-700">.</span></Link><Link href="/explore" className="text-sm font-semibold text-emerald-800 hover:underline">Explore funding</Link></header>
    <div className="mx-auto grid max-w-6xl gap-12 px-5 pb-20 pt-12 sm:px-8 lg:grid-cols-[1fr_450px] lg:items-center lg:pt-24">
      <div><div className="mb-6 inline-flex items-center gap-2 rounded-full bg-emerald-100 px-3 py-1.5 text-xs font-bold uppercase tracking-[0.16em] text-emerald-900"><Sparkles size={14}/> Local demo mode</div><h1 className="max-w-2xl text-5xl font-semibold leading-[1.08] tracking-tight sm:text-6xl">Your business story starts here.</h1><p className="mt-7 max-w-xl text-lg leading-8 text-slate-600">Build one reusable profile for funding discovery, future eligibility guidance, and application support. You can skip questions and come back anytime during this local demo.</p><div className="mt-9 grid max-w-xl gap-3 sm:grid-cols-3">{["Tell us about you", "Describe your business", "Set funding goals"].map((item, index) => <div key={item} className="rounded-xl border border-emerald-100 bg-white/70 p-4 text-sm font-medium text-slate-700"><span className="mb-2 block text-2xl font-semibold text-emerald-800">0{index + 1}</span>{item}</div>)}</div></div>
      <div className="rounded-[2rem] border border-emerald-100 bg-white p-7 shadow-[0_24px_70px_-35px_rgba(4,76,54,.35)] sm:p-9"><div className="text-xs font-bold uppercase tracking-[0.18em] text-emerald-700">Get started</div><h2 className="mt-3 text-2xl font-semibold tracking-tight">Create a demo founder</h2><p className="mt-2 text-sm leading-6 text-slate-500">No email or password needed. Your profile stays private in this development environment.</p><label className="mt-7 block text-sm font-semibold text-slate-800" htmlFor="display-name">Your display name <span className="font-normal text-slate-400">(optional)</span></label><input id="display-name" value={name} onChange={event => setName(event.target.value)} maxLength={200} placeholder="e.g. Alex" className="mt-2 h-12 w-full rounded-xl border border-slate-200 px-4 outline-none focus:border-emerald-700 focus:ring-2 focus:ring-emerald-100"/><button disabled={busy} onClick={() => create(false, true)} className="mt-5 flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-emerald-800 font-semibold text-white transition hover:bg-emerald-900 disabled:opacity-60">{busy ? "Creating profile…" : "Start with Seedline Assistant"}<Sparkles size={18}/></button><button disabled={busy} onClick={() => create(false)} className="mt-3 flex h-12 w-full items-center justify-center gap-2 rounded-xl border border-emerald-200 bg-white font-semibold text-emerald-900 transition hover:bg-emerald-50 disabled:opacity-60">Use manual form <ArrowRight size={18}/></button><div className="my-7 flex items-center gap-3 text-xs font-semibold uppercase tracking-widest text-slate-400"><span className="h-px flex-1 bg-slate-200"/>or explore a sample<span className="h-px flex-1 bg-slate-200"/></div><button disabled={busy} onClick={() => create(true)} className="flex h-12 w-full items-center justify-center rounded-xl border border-emerald-200 bg-emerald-50 font-semibold text-emerald-900 transition hover:bg-emerald-100 disabled:opacity-60">View example founder</button>{error && <p role="alert" className="mt-4 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}</div>
    </div>
  </main>;
}
