"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Check, Leaf, MessageCircle, Send, Sparkles, X } from "lucide-react";
import { demoRequest, loadDemo } from "@/lib/demo-client";
import { OPTIONS, type DemoContext } from "@/lib/demo-types";
import { FIELD_LABELS, STATUS_LABELS, type Recommendation, type RecommendationList } from "@/lib/recommendations";
import type { AssistantConversation, AssistantSuggestion } from "@/lib/assistant";

type OptionList = readonly (readonly [string, string])[];
const options: Record<string, OptionList> = {
  industry: OPTIONS.industry, business_stage: OPTIONS.stage, legal_structure: OPTIONS.legal,
  incorporation_status: OPTIONS.incorporation, funding_purposes: OPTIONS.purposes,
  preferred_funding_types: OPTIONS.types, annual_revenue_range: OPTIONS.revenue,
  country: [["CA", "Canada"], ["US", "United States"]],
};
const arrays = new Set(["industry", "funding_purposes", "preferred_funding_types"]);
const numbers = new Set(["employee_count", "year_established", "years_in_operation", "amount_min", "amount_max"]);
const resources: Record<string, string> = {
  name: "organization", description: "organization", country: "organization", province: "organization", city: "organization",
  industry: "organization", business_stage: "organization", legal_structure: "organization",
  incorporation_status: "organization", year_established: "organization", employee_count: "details",
  years_in_operation: "details", annual_revenue_range: "details", funding_purposes: "funding-intent",
  amount_min: "funding-intent", amount_max: "funding-intent", project_description: "funding-intent",
  preferred_funding_types: "funding-intent",
};
const profileFields = ["name", "description", "country", "province", "city", "industry", "business_stage",
  "legal_structure", "incorporation_status", "year_established", "years_in_operation", "employee_count",
  "annual_revenue_range", "funding_purposes", "project_description", "preferred_funding_types", "amount_min", "amount_max"];
const inputClass = "w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-emerald-700";

function label(field: string) {
  return FIELD_LABELS[field] ?? ({ description: "Business description", country: "Business country", province: "Province",
    city: "City", name: "Business name", project_description: "Funding project", amount_min: "Funding from",
    amount_max: "Funding up to", preferred_funding_types: "Preferred funding types" } as Record<string, string>)[field] ?? field.replaceAll("_", " ");
}

function formatted(field: string, value: unknown): string {
  if (value === null || value === undefined || value === "" || Array.isArray(value) && !value.length) return "Not provided";
  if (Array.isArray(value)) return value.map(item => options[field]?.find(([key]) => key === item)?.[1] ?? item).join(", ");
  if (typeof value === "number" && field.startsWith("amount")) return new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD", maximumFractionDigits: 0 }).format(value);
  return options[field]?.find(([key]) => key === value)?.[1] ?? String(value);
}

function ValueInput({ field, value, onChange }: { field: string; value: unknown; onChange: (value: unknown) => void }) {
  if (arrays.has(field)) return <div className="flex flex-wrap gap-1.5">{options[field].map(([key, title]) => {
    const selected = Array.isArray(value) && value.includes(key);
    return <button key={key} type="button" aria-pressed={selected} onClick={() => onChange(selected ? (value as string[]).filter(item => item !== key) : [...(Array.isArray(value) ? value : []), key])}
      className={`rounded-full border px-2.5 py-1.5 text-xs font-medium ${selected ? "border-emerald-700 bg-emerald-700 text-white" : "border-slate-200 bg-white text-slate-600"}`}>{title}</button>;
  })}</div>;
  if (options[field]) return <select aria-label={label(field)} className={inputClass} value={String(value ?? "")} onChange={event => onChange(event.target.value || null)}>
    <option value="">Select</option>{options[field].map(([key, title]) => <option key={key} value={key}>{title}</option>)}
  </select>;
  if (field === "description" || field === "project_description") return <textarea aria-label={label(field)} rows={3} maxLength={10000} className={inputClass} value={String(value ?? "")} onChange={event => onChange(event.target.value || null)}/>;
  return <input aria-label={label(field)} className={inputClass} type={numbers.has(field) ? "number" : "text"}
    min={numbers.has(field) ? 0 : undefined} value={value === null || value === undefined ? "" : String(value)}
    onChange={event => onChange(numbers.has(field) ? event.target.value === "" ? null : Number(event.target.value) : event.target.value || null)}/>;
}

function ProfileEditor({ field, value, provenance, pending, busy, onSave }: { field: string; value: unknown;
  provenance?: string; pending: boolean; busy: boolean; onSave: (field: string, value: unknown) => Promise<boolean> }) {
  const [draft, setDraft] = useState<unknown>(value);
  const [editing, setEditing] = useState(false);
  const changed = JSON.stringify(draft) !== JSON.stringify(value);
  return <div className={`rounded-xl border p-3 ${pending ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white"}`}>
    <div className="flex items-center justify-between gap-2"><span className="text-xs font-semibold text-slate-700">{label(field)}</span>
      <span className="text-[10px] font-semibold text-slate-500">{pending ? "AI suggestion" : provenance === "ai_confirmed" ? "AI · confirmed" : provenance === "manual" ? "Manual" : ""}</span></div>
    {editing ? <div className="mt-2"><ValueInput field={field} value={draft} onChange={setDraft}/><div className="mt-2 flex items-center gap-3"><button type="button" disabled={busy || !changed} onClick={() => void onSave(field, draft).then(saved => { if (saved) setEditing(false); })} className="text-xs font-bold text-emerald-800 disabled:opacity-50">Save change</button><button type="button" onClick={() => { setDraft(value); setEditing(false); }} className="text-xs text-slate-500">Cancel</button></div></div> :
      <div className="mt-2 flex items-start justify-between gap-2"><p className="line-clamp-3 text-sm text-slate-800">{formatted(field, value)}</p><button type="button" onClick={() => setEditing(true)} className="shrink-0 text-xs font-bold text-emerald-800 hover:underline">Edit</button></div>}
  </div>;
}

export function AssistantWorkspace({ opportunityId }: { opportunityId?: string }) {
  const [conversation, setConversation] = useState<AssistantConversation | null>(null);
  const [profile, setProfile] = useState<DemoContext | null>(null);
  const [matches, setMatches] = useState<RecommendationList | null>(null);
  const [opportunity, setOpportunity] = useState<Recommendation | null>(null);
  const [drafts, setDrafts] = useState<Record<string, unknown>>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async (next?: AssistantConversation) => {
    const [context, listing, detail] = await Promise.all([
      loadDemo(), demoRequest<RecommendationList>("recommendations"),
      opportunityId ? demoRequest<Recommendation>(`recommendations/${opportunityId}`) : Promise.resolve(null),
    ]);
    setProfile(context); setMatches(listing); setOpportunity(detail);
    if (next) setConversation(next);
  }, [opportunityId]);

  useEffect(() => {
    let active = true;
    demoRequest<AssistantConversation>("assistant/conversations", "POST", { opportunity_id: opportunityId ?? null })
      .then(async result => { if (active) { setConversation(result); await refresh(); } })
      .catch(cause => { if (active) setError(cause instanceof Error ? cause.message : "Assistant unavailable"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [opportunityId, refresh]);

  const pending = conversation?.suggestions.filter(item => item.status === "pending") ?? [];
  const valueOf = (item: AssistantSuggestion) => drafts[item.id] === undefined ? item.value : drafts[item.id];

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!conversation || !message.trim() || busy || pending.length) return;
    setBusy(true); setError("");
    try {
      const result = await demoRequest<AssistantConversation>(`assistant/conversations/${conversation.id}/messages`, "POST",
        { request_id: crypto.randomUUID(), content: message.trim() });
      setMessage(""); setDrafts({}); await refresh(result);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not process your answer"); }
    finally { setBusy(false); }
  }

  async function decide(items: AssistantSuggestion[], action: "accept" | "reject") {
    if (!conversation || busy) return;
    setBusy(true); setError("");
    try {
      const result = await demoRequest<AssistantConversation>(`assistant/conversations/${conversation.id}/confirm`, "POST", {
        decisions: items.map(item => ({ id: item.id, action, ...(action === "accept" ? { value: valueOf(item) } : {}) })),
      });
      setDrafts({}); await refresh(result);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not confirm suggestions"); }
    finally { setBusy(false); }
  }

  async function skip() {
    if (!conversation || busy) return;
    setBusy(true); setError("");
    try { const result = await demoRequest<AssistantConversation>(`assistant/conversations/${conversation.id}/skip`, "POST"); setConversation(result); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not skip"); }
    finally { setBusy(false); }
  }

  async function saveProfile(field: string, value: unknown): Promise<boolean> {
    setBusy(true); setError("");
    try {
      await demoRequest(resources[field], "PATCH", { [field]: value });
      if (conversation) {
        const last = conversation.messages.at(-1);
        const path = `assistant/conversations/${conversation.id}`;
        const updated = last?.role === "assistant" && last.target_field === field && !pending.length ?
          await demoRequest<AssistantConversation>(`${path}/skip`, "POST") :
          await demoRequest<AssistantConversation>(path);
        await refresh(updated);
      } else await refresh();
      return true;
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not save profile"); return false; }
    finally { setBusy(false); }
  }

  if (loading) return <div className="grid min-h-screen place-items-center bg-[#f6f8f5] text-sm text-slate-500">Opening Seedline Assistant…</div>;
  if (!conversation || !profile) return <div className="grid min-h-screen place-items-center bg-[#f6f8f5] p-6"><div role="alert" className="rounded-2xl bg-white p-8 text-sm text-rose-800">{error || "No demo profile found."} <Link href="/demo" className="font-bold underline">Start a demo profile</Link></div></div>;

  const back = opportunityId ? `/recommendations/${opportunityId}` : "/onboarding";
  return <div className="min-h-screen bg-[#f6f8f5] text-slate-900">
    <header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-5 py-4 sm:px-8"><Link href="/explore" className="flex items-center gap-2 text-xl font-bold"><span className="grid size-9 place-items-center rounded-xl bg-emerald-800 text-white"><Leaf size={20}/></span>Seedline<span className="text-emerald-700">.</span></Link><nav className="flex items-center gap-4 text-sm font-semibold"><Link href={back} className="text-emerald-800 hover:underline"><ArrowLeft size={14} className="inline"/> {opportunityId ? "Back to opportunity" : "Manual onboarding"}</Link><Link href="/recommendations" className="hidden text-slate-600 hover:text-emerald-800 sm:inline">Recommendations</Link></nav></div></header>
    <main className="mx-auto max-w-7xl px-5 pb-16 pt-8 sm:px-8"><div className="mb-7 flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-widest text-emerald-700">Conversational onboarding</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">Build your profile with Seedline</h1><p className="mt-2 text-sm text-slate-600">Describe your business naturally. Review every suggested change before it is saved.</p></div><div className="rounded-full bg-amber-50 px-3 py-2 text-xs font-bold text-amber-900">{conversation.mode === "mock" ? "Deterministic mock · local demo" : "Live AI · OpenRouter"}</div></div>
      {error && <p role="alert" className="mb-5 rounded-xl bg-rose-50 p-4 text-sm text-rose-800">{error}</p>}
      <div className="grid gap-6 lg:grid-cols-[minmax(310px,.9fr)_minmax(420px,1.1fr)] lg:items-start">
        <section aria-label="Business profile" className="rounded-[1.5rem] border border-slate-200 bg-white p-5 shadow-sm sm:p-6"><div className="flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-widest text-emerald-700">Business profile</p><h2 className="mt-1 text-xl font-semibold">Your confirmed details</h2></div><span className="text-2xl font-bold text-emerald-800">{profile.completion.overall_completion}%</span></div><div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100"><div className="h-full bg-emerald-700 transition-all" style={{ width: `${profile.completion.overall_completion}%` }}/></div><p className="mt-2 text-xs text-slate-500">Only confirmed answers affect your funding assessment.</p>
          <div className="mt-6 grid gap-3 sm:grid-cols-2">{profileFields.map(field => {
            const resource = resources[field];
            const data = resource === "organization" ? profile.organization : resource === "details" ? profile.details : profile.funding_intent;
            const value = (data as unknown as Record<string, unknown>)[field];
            return <ProfileEditor key={`${field}:${JSON.stringify(value)}`} field={field} value={value}
              provenance={conversation.provenance[field]} pending={pending.some(item => item.field === field)}
              busy={busy} onSave={saveProfile}/>;
          })}</div><Link href="/onboarding" className="mt-5 inline-flex items-center gap-1 text-sm font-bold text-emerald-800 hover:underline">Open full manual form <ArrowRight size={14}/></Link>
        </section>
        <section aria-label="Seedline Assistant" className="rounded-[1.5rem] border border-emerald-200 bg-white shadow-sm"><div className="flex items-center justify-between border-b border-slate-100 p-5 sm:p-6"><div className="flex items-center gap-3"><span className="grid size-10 place-items-center rounded-xl bg-emerald-800 text-white"><MessageCircle size={20}/></span><div><h2 className="font-semibold">Seedline Assistant</h2><p className="text-xs text-slate-500">{conversation.opportunity_title ? `Discussing ${conversation.opportunity_title}` : "Learning about your business"}</p></div></div><Sparkles size={19} className="text-emerald-700"/></div>
          <div aria-live="polite" className="max-h-[480px] space-y-4 overflow-y-auto bg-[#fbfcfa] p-5 sm:p-6">{conversation.messages.map(item => <div key={item.id} className={`flex ${item.role === "user" ? "justify-end" : "justify-start"}`}><div className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-6 ${item.role === "user" ? "bg-emerald-800 text-white" : "border border-slate-200 bg-white text-slate-800"}`}>{item.content}</div></div>)}{busy && <div className="text-xs text-slate-500">Seedline is working…</div>}</div>
          {pending.length > 0 && <div className="border-t border-amber-200 bg-amber-50/50 p-5 sm:p-6"><div className="flex flex-wrap items-center justify-between gap-2"><div><h3 className="font-semibold">Review suggested updates</h3><p className="mt-1 text-xs text-slate-600">Suggestions are based on your answer. Edit or reject anything that is inaccurate.</p></div><button type="button" disabled={busy} onClick={() => void decide(pending, "accept")} className="rounded-lg bg-emerald-800 px-3 py-2 text-xs font-bold text-white disabled:opacity-50">Accept all</button></div><div className="mt-4 space-y-3">{pending.map(item => <div key={item.id} className="rounded-xl border border-amber-200 bg-white p-4"><div className="flex items-center justify-between gap-2"><span className="text-sm font-semibold">{label(item.field)}</span><span className="text-xs text-slate-500">{item.confidence} confidence</span></div><p className="mt-1 text-xs text-slate-500">You said: “{item.source_text}”</p><p className="mt-2 text-xs text-slate-500">Current: {formatted(item.field, item.base_value)}</p><div className="mt-2"><ValueInput field={item.field} value={valueOf(item)} onChange={value => setDrafts(previous => ({ ...previous, [item.id]: value }))}/></div><div className="mt-3 flex gap-4"><button type="button" disabled={busy} onClick={() => void decide([item], "accept")} className="inline-flex items-center gap-1 text-xs font-bold text-emerald-800 disabled:opacity-50"><Check size={13}/>Accept</button><button type="button" disabled={busy} onClick={() => void decide([item], "reject")} className="inline-flex items-center gap-1 text-xs font-bold text-rose-700 disabled:opacity-50"><X size={13}/>Reject</button></div></div>)}</div></div>}
          <form onSubmit={submit} className="border-t border-slate-100 p-5 sm:p-6"><label htmlFor="founder-answer" className="text-sm font-semibold">Your answer</label><textarea id="founder-answer" value={message} onChange={event => setMessage(event.target.value)} rows={3} maxLength={4000} disabled={busy || pending.length > 0} placeholder={pending.length ? "Review suggestions to continue" : "Tell Seedline about your business…"} className={`mt-2 ${inputClass} disabled:bg-slate-50`}/><div className="mt-3 flex items-center justify-between"><button type="button" onClick={() => void skip()} disabled={busy || pending.length > 0} className="text-xs font-semibold text-slate-500 hover:text-emerald-800 disabled:opacity-40">Skip question</button><button type="submit" disabled={busy || pending.length > 0 || !message.trim()} className="inline-flex items-center gap-2 rounded-xl bg-emerald-800 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-900 disabled:opacity-40">Send answer <Send size={15}/></button></div></form>
          {opportunity && <div className="border-t border-slate-100 bg-emerald-50 p-5 text-sm"><p className="font-semibold">Current assessment: {STATUS_LABELS[opportunity.eligibility_status]}</p><p className="mt-1 text-slate-600">{opportunity.missing_profile_fields.length ? `Still need: ${opportunity.missing_profile_fields.map(label).join(", ")}.` : "No profile fields are currently missing for this assessment."}</p><Link href={`/recommendations/${opportunityId}`} className="mt-2 inline-block font-bold text-emerald-800 hover:underline">View updated opportunity →</Link></div>}
        </section>
      </div>
      {matches?.ready && <section className="mt-7 rounded-[1.5rem] border border-slate-200 bg-white p-6"><div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-xl font-semibold">Funding matches from your confirmed profile</h2><p className="mt-1 text-sm text-slate-600">{matches.potentially_relevant_count} potentially relevant opportunities. Pending suggestions do not affect this list.</p></div><Link href="/recommendations" className="text-sm font-bold text-emerald-800 hover:underline">View all recommendations →</Link></div><div className="mt-4 grid gap-3 md:grid-cols-2">{matches.items.filter(item => item.eligibility_status !== "potentially_ineligible").slice(0, 2).map(item => <Link href={`/recommendations/${item.opportunity_id}`} key={item.opportunity_id} className="rounded-xl border border-emerald-100 bg-emerald-50 p-4 hover:border-emerald-400"><p className="font-semibold">{item.opportunity.title}</p><p className="mt-1 text-xs text-emerald-900">{item.relevance_score}/100 relevance · {STATUS_LABELS[item.eligibility_status]}</p></Link>)}</div></section>}
    </main>
  </div>;
}
