"use client";

import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, Check, CircleHelp, Leaf, RotateCcw } from "lucide-react";
import { demoRequest, loadDemo } from "@/lib/demo-client";
import { OPTIONS, SECTION_META, type Completion, type DemoContext, type SectionId } from "@/lib/demo-types";

type DataKey = "founder" | "organization" | "funding_intent" | "details" | "interests";
type SaveState = "saved" | "saving" | "error";
const resource: Record<DataKey, string> = { founder: "founder", organization: "organization", funding_intent: "funding-intent", details: "details", interests: "interests" };
const inputClass = "mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3.5 text-sm text-slate-900 outline-none transition focus:border-emerald-700 focus:ring-2 focus:ring-emerald-100";
const cardClass = "rounded-[1.6rem] border border-slate-200 bg-white p-6 shadow-sm sm:p-8";

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return <div><div className="text-sm font-semibold text-slate-800">{label}</div>{hint && <p className="mt-1 text-xs leading-5 text-slate-500">{hint}</p>}{children}</div>;
}

function TextField({ label, hint, value, onChange, type = "text", placeholder, maxLength = 200 }: { label: string; hint?: string; value: string | null; onChange: (value: string | null) => void; type?: string; placeholder?: string; maxLength?: number }) {
  return <Field label={label} hint={hint}><input aria-label={label} type={type} value={value ?? ""} onChange={event => onChange(event.target.value || null)} placeholder={placeholder} maxLength={maxLength} className={inputClass}/></Field>;
}

function TextArea({ label, hint, value, onChange, placeholder }: { label: string; hint?: string; value: string | null; onChange: (value: string | null) => void; placeholder?: string }) {
  return <Field label={label} hint={hint}><textarea aria-label={label} value={value ?? ""} onChange={event => onChange(event.target.value || null)} placeholder={placeholder} rows={4} maxLength={10000} className={`${inputClass} h-auto min-h-28 py-3`}/></Field>;
}

function SelectField({ label, hint, value, options, onChange }: { label: string; hint?: string; value: string | null; options: readonly (readonly [string, string])[]; onChange: (value: string | null) => void }) {
  return <Field label={label} hint={hint}><select aria-label={label} value={value ?? ""} onChange={event => onChange(event.target.value || null)} className={inputClass}><option value="">Select an option</option>{options.map(([id, title]) => <option key={id} value={id}>{title}</option>)}</select></Field>;
}

function CountryField({ value, onChange }: { value: string | null; onChange: (value: string | null) => void }) {
  const [other, setOther] = useState(false);
  const selected = value && !["CA", "US"].includes(value) ? "other" : other ? "other" : value;
  return <div><SelectField label="Country" value={selected} options={[["CA", "Canada"], ["US", "United States"], ["other", "Other country"]]} onChange={next => { setOther(next === "other"); onChange(next === "other" ? null : next); }}/>{selected === "other" && <input aria-label="Two-letter country code" value={value && !["CA", "US"].includes(value) ? value : ""} onChange={event => onChange(event.target.value.toUpperCase() || null)} maxLength={2} placeholder="Two-letter country code, e.g. GB" className={inputClass}/>}</div>;
}

function MultiSelect({ label, hint, value, options, onChange, searchable = false }: { label: string; hint?: string; value: string[]; options: readonly (readonly [string, string])[]; onChange: (value: string[]) => void; searchable?: boolean }) {
  const [search, setSearch] = useState("");
  const shown = options.filter(([, title]) => title.toLowerCase().includes(search.toLowerCase()));
  return <Field label={label} hint={hint}><div className="mt-3 rounded-xl border border-slate-200 p-3">{searchable && <input aria-label={`Search ${label.toLowerCase()}`} value={search} onChange={event => setSearch(event.target.value)} placeholder="Search categories" className="mb-3 h-9 w-full rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-emerald-700"/>}<div className="flex flex-wrap gap-2">{shown.map(([id, title]) => { const selected = value.includes(id); return <button type="button" key={id} aria-pressed={selected} onClick={() => onChange(selected ? value.filter(item => item !== id) : [...value, id])} className={`rounded-full border px-3.5 py-2 text-sm font-medium transition ${selected ? "border-emerald-800 bg-emerald-800 text-white" : "border-slate-200 bg-white text-slate-600 hover:border-emerald-500 hover:text-emerald-800"}`}>{selected && <Check size={13} className="mr-1 inline"/>}{title}</button>; })}{shown.length === 0 && <p className="px-1 py-2 text-sm text-slate-500">No categories found</p>}</div></div></Field>;
}

function NumberField({ label, value, onChange, placeholder }: { label: string; value: number | null; onChange: (value: number | null) => void; placeholder?: string }) {
  return <Field label={label}><input aria-label={label} type="number" min="0" value={value ?? ""} onChange={event => onChange(event.target.value === "" ? null : Number(event.target.value))} placeholder={placeholder} className={inputClass}/></Field>;
}

function AnswerChoice({ label, value, onChange, hint }: { label: string; value: boolean | null; onChange: (value: boolean | null) => void; hint?: string }) {
  return <SelectField label={label} hint={hint} value={value === null ? null : value ? "yes" : "no"} options={[["yes", "Yes"], ["no", "No"], ["unsure", "Unsure / not answered"]]} onChange={next => onChange(next === "yes" ? true : next === "no" ? false : null)}/>;
}

export function OnboardingWizard({ initialStep }: { initialStep?: SectionId }) {
  const router = useRouter();
  const [context, setContext] = useState<DemoContext | null>(null);
  const [step, setStep] = useState<SectionId>(initialStep ?? "founder_basics");
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const pending = useRef<Partial<Record<DataKey, Record<string, unknown>>>>({});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const active = useRef<Promise<boolean> | null>(null);
  const revision = useRef(0);

  useEffect(() => { loadDemo().then(async data => {
    setContext(data);
    setStep(initialStep ?? data.onboarding.current_step);
    if (initialStep && initialStep !== data.onboarding.current_step) await demoRequest("onboarding", "PATCH", { current_step: initialStep });
  }).catch(cause => setError(cause instanceof Error ? cause.message : "Could not load profile")).finally(() => setLoading(false)); }, [initialStep]);
  useEffect(() => {
    function warnBeforeUnload(event: BeforeUnloadEvent) {
      if (Object.keys(pending.current).length || active.current) event.preventDefault();
    }
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, []);

  const flush = useCallback(async (): Promise<boolean> => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    while (true) {
      if (active.current) { if (!await active.current) return false; }
      if (!Object.keys(pending.current).length) return true;
      const batch = pending.current;
      pending.current = {};
      const version = revision.current;
      setSaveState("saving");
      const work = (async () => {
        try {
          for (const key of Object.keys(batch) as DataKey[]) await demoRequest(resource[key], "PATCH", batch[key]);
          if (version === revision.current) {
            const completion = await demoRequest<Completion>("completion");
            if (version === revision.current) setContext(previous => previous ? { ...previous, completion } : previous);
          }
          setSaveState(Object.keys(pending.current).length ? "saving" : "saved");
          setError("");
          return true;
        } catch (cause) {
          pending.current = Object.fromEntries(Object.entries(batch).map(([key, fields]) => [key, { ...fields, ...(pending.current[key as DataKey] ?? {}) }])) as typeof pending.current;
          setSaveState("error");
          setError(cause instanceof Error ? cause.message : "Unable to save. Retry.");
          return false;
        }
      })();
      active.current = work;
      const success = await work;
      if (active.current === work) active.current = null;
      if (!success) return false;
    }
  }, []);

  function update(section: DataKey, key: string, value: unknown) {
    revision.current += 1;
    setContext(previous => previous ? { ...previous, [section]: { ...previous[section], [key]: value } } : previous);
    pending.current[section] = { ...(pending.current[section] ?? {}), [key]: value };
    setSaveState("saving");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => { void flush(); }, 600);
  }

  function leave(event: MouseEvent<HTMLAnchorElement>, href: string) {
    event.preventDefault();
    void flush().then(ok => { if (ok) router.push(href); });
  }

  async function go(next: SectionId | "dashboard", sectionStatus?: "completed" | "skipped") {
    if (!await flush()) return;
    try {
      await demoRequest("onboarding", "PATCH", {
        current_step: step,
        ...(sectionStatus ? { section_status: sectionStatus } : {}),
        ...(next === "dashboard" ? { onboarding_status: "finished" } : {}),
      });
      if (next === "dashboard") { router.push("/dashboard"); router.refresh(); return; }
      await demoRequest("onboarding", "PATCH", { current_step: next });
      setStep(next);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not update progress"); }
  }

  async function reset() {
    if (!window.confirm("Start a new, empty demo profile? Your current demo profile will remain in the local database.")) return;
    if (!await flush()) return;
    try { await demoRequest("reset", "POST"); router.replace(`/onboarding?fresh=${Date.now()}`); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not start fresh"); }
  }

  if (loading) return <div className="grid min-h-screen place-items-center bg-[#f6f8f5] text-sm font-medium text-slate-500">Loading your Seedline profile…</div>;
  if (!context) return <div className="grid min-h-screen place-items-center bg-[#f6f8f5] px-5"><div className="max-w-md rounded-2xl bg-white p-8 text-center shadow-sm"><p role="alert" className="text-slate-700">{error || "No demo profile found."}</p><Link href="/demo" className="mt-5 inline-block font-semibold text-emerald-800">Create a demo profile →</Link></div></div>;

  const value = (section: DataKey, key: string) => (context[section] as unknown as Record<string, unknown>)[key];
  const string = (section: DataKey, key: string) => value(section, key) as string | null;
  const list = (section: DataKey, key: string) => (value(section, key) as string[] | null) ?? [];
  const number = (section: DataKey, key: string) => value(section, key) as number | null;
  const bool = (section: DataKey, key: string) => value(section, key) as boolean | null;
  const index = SECTION_META.findIndex(item => item.id === step);
  const current = SECTION_META[index];
  const stepCompletion = context.completion.sections.find(section => section.id === step)?.completion ?? 0;

  return <div className="min-h-screen bg-[#f6f8f5] text-slate-900">
    <header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 sm:px-8"><Link href="/explore" onClick={event => leave(event, "/explore")} className="flex items-center gap-2 text-xl font-bold tracking-tight"><span className="grid size-9 place-items-center rounded-xl bg-emerald-800 text-white"><Leaf size={20}/></span>Seedline<span className="text-emerald-700">.</span></Link><div className="flex items-center gap-4"><span className="hidden rounded-full bg-amber-50 px-3 py-1 text-xs font-bold uppercase tracking-wide text-amber-800 sm:inline">Local demo mode</span><Link href="/dashboard" onClick={event => leave(event, "/dashboard")} className="text-sm font-semibold text-emerald-800 hover:underline">View dashboard</Link></div></div></header>
    <div className="mx-auto max-w-7xl px-5 py-8 sm:px-8 lg:py-12"><div className="mb-9 flex flex-wrap items-end justify-between gap-5"><div><div className="text-xs font-bold uppercase tracking-[0.18em] text-emerald-800">Your reusable business profile</div><h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Let&apos;s get to know your business.</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">Answer what you can today. Your progress saves as you go, and you can return to any section.</p></div><div className="rounded-2xl border border-emerald-100 bg-white px-5 py-3 text-right"><div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Profile coverage</div><div className="text-2xl font-semibold text-emerald-800">{context.completion.overall_completion}%</div></div></div>
      <div className="grid gap-8 lg:grid-cols-[255px_minmax(0,1fr)]"><aside className="lg:sticky lg:top-6 lg:self-start"><nav aria-label="Onboarding sections" className="grid grid-cols-2 gap-2 sm:grid-cols-5 lg:grid-cols-1">{SECTION_META.map((item, position) => { const activeStep = item.id === step; const score = context.completion.sections.find(section => section.id === item.id)?.completion ?? 0; return <button type="button" key={item.id} onClick={() => { void go(item.id); }} className={`rounded-xl border p-3 text-left transition sm:p-4 ${activeStep ? "border-emerald-700 bg-emerald-800 text-white shadow-md" : "border-slate-200 bg-white text-slate-700 hover:border-emerald-300"}`}><div className="flex items-center justify-between"><span className={`text-xs font-bold uppercase tracking-wider ${activeStep ? "text-emerald-100" : "text-emerald-700"}`}>0{position + 1}</span><span className={`text-xs font-semibold ${activeStep ? "text-emerald-100" : "text-slate-400"}`}>{score}%</span></div><div className="mt-2 text-sm font-semibold">{item.title}</div><div className={`mt-2 h-1 rounded-full ${activeStep ? "bg-emerald-600" : "bg-slate-100"}`}><div className={`h-1 rounded-full ${activeStep ? "bg-white" : "bg-emerald-700"}`} style={{ width: `${score}%` }}/></div></button>; })}</nav><button type="button" onClick={reset} className="mt-5 flex items-center gap-2 text-xs font-semibold text-slate-500 hover:text-emerald-800"><RotateCcw size={14}/>Start Fresh Demo</button></aside>
        <main><div className={cardClass}><div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 pb-6"><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-emerald-700">Section {index + 1} of 5</p><h2 className="mt-2 text-2xl font-semibold tracking-tight">{current.title}</h2><p className="mt-2 text-sm leading-6 text-slate-600">{current.description}</p></div><span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-800">{stepCompletion}% filled</span></div>
          <div className="grid gap-6 py-7 sm:grid-cols-2">
            {step === "founder_basics" && <><TextField label="Display name" value={string("founder", "display_name")} onChange={v => update("founder", "display_name", v)} placeholder="How should we address you?"/><TextField label="Your role in the business" value={string("founder", "role")} onChange={v => update("founder", "role", v)} placeholder="e.g. Founder, CEO"/><TextField label="City" value={string("founder", "city")} onChange={v => update("founder", "city", v)}/><TextField label="Province or state" value={string("founder", "province")} onChange={v => update("founder", "province", v)} placeholder="e.g. Quebec"/><CountryField value={string("founder", "country")} onChange={v => update("founder", "country", v)}/><TextField label="LinkedIn URL" hint="Optional. This stays private in your profile." type="url" value={string("founder", "linkedin_url")} onChange={v => update("founder", "linkedin_url", v)} placeholder="https://linkedin.com/in/…"/><div className="sm:col-span-2"><TextArea label="Professional background" value={string("founder", "professional_background")} onChange={v => update("founder", "professional_background", v)} placeholder="A short summary of your experience"/></div></>}
            {step === "business_overview" && <><TextField label="Business name" value={string("organization", "name")} onChange={v => update("organization", "name", v ?? "")} placeholder="Your business or working name"/><TextField label="Website" type="url" value={string("organization", "website")} onChange={v => update("organization", "website", v)} placeholder="https://…"/><div className="sm:col-span-2"><TextArea label="What does your business do?" value={string("organization", "description")} onChange={v => update("organization", "description", v)} placeholder="Describe your product, service, or mission in a few sentences"/></div><div className="sm:col-span-2"><MultiSelect label="Industries" hint="Choose all that fit. These broad categories help us organize future funding discovery." searchable value={list("organization", "industry")} options={OPTIONS.industry} onChange={v => update("organization", "industry", v)}/></div><SelectField label="Business stage" value={string("organization", "business_stage")} options={OPTIONS.stage} onChange={v => update("organization", "business_stage", v)}/><SelectField label="Business model" value={string("organization", "business_model")} options={OPTIONS.businessModel} onChange={v => update("organization", "business_model", v)}/><CountryField value={string("organization", "country")} onChange={v => update("organization", "country", v ?? "")}/><TextField label="Province or state" value={string("organization", "province")} onChange={v => update("organization", "province", v)}/><TextField label="City" value={string("organization", "city")} onChange={v => update("organization", "city", v)}/><SelectField label="Legal structure" value={string("organization", "legal_structure")} options={OPTIONS.legal} onChange={v => update("organization", "legal_structure", v)}/><SelectField label="Incorporation status" value={string("organization", "incorporation_status")} options={OPTIONS.incorporation} onChange={v => { update("organization", "incorporation_status", v); if (v === "not_incorporated") update("organization", "year_established", null); }}/>{string("organization", "incorporation_status") === "incorporated" && <NumberField label="Year established" value={number("organization", "year_established")} onChange={v => update("organization", "year_established", v)} placeholder="e.g. 2023"/>}</>}
            {step === "funding_goals" && <><div className="sm:col-span-2"><MultiSelect label="What are you hoping to fund?" value={list("funding_intent", "funding_purposes")} options={OPTIONS.purposes} onChange={v => update("funding_intent", "funding_purposes", v)}/></div><div className="sm:col-span-2"><label className="flex items-center gap-3 rounded-xl bg-emerald-50 p-4 text-sm font-medium text-emerald-950"><input type="checkbox" checked={bool("funding_intent", "amount_unsure") === true} onChange={event => { update("funding_intent", "amount_unsure", event.target.checked); if (event.target.checked) { update("funding_intent", "amount_min", null); update("funding_intent", "amount_max", null); } }} className="size-4 accent-emerald-800"/>I&apos;m unsure about the amount</label></div>{bool("funding_intent", "amount_unsure") !== true && <><NumberField label="Minimum amount (CAD)" value={number("funding_intent", "amount_min")} onChange={v => update("funding_intent", "amount_min", v)} placeholder="e.g. 25000"/><NumberField label="Maximum amount (CAD)" value={number("funding_intent", "amount_max")} onChange={v => update("funding_intent", "amount_max", v)} placeholder="e.g. 100000"/></>}<SelectField label="Funding timeline" value={string("funding_intent", "funding_timeline")} options={OPTIONS.timeline} onChange={v => update("funding_intent", "funding_timeline", v)}/><div className="sm:col-span-2"><MultiSelect label="Preferred funding types" value={list("funding_intent", "preferred_funding_types")} options={OPTIONS.types} onChange={v => update("funding_intent", "preferred_funding_types", v)}/></div><div className="sm:col-span-2"><TextArea label="Project or intended use of funds" value={string("funding_intent", "project_description")} onChange={v => update("funding_intent", "project_description", v)} placeholder="What would this funding help you accomplish?"/></div></>}
            {step === "business_details" && <><NumberField label="Number of employees" value={number("details", "employee_count")} onChange={v => update("details", "employee_count", v)} placeholder="Include yourself if applicable"/>{context.organization.incorporation_status !== "incorporated" && <NumberField label="Years in operation" value={number("details", "years_in_operation")} onChange={v => update("details", "years_in_operation", v)} placeholder="Approximate years active"/>}<SelectField label="Annual revenue range" hint="Pre-revenue is a valid answer for idea-stage businesses." value={string("details", "annual_revenue_range")} options={OPTIONS.revenue} onChange={v => update("details", "annual_revenue_range", v)}/><SelectField label="Received grants or government funding before?" value={string("details", "previous_funding")} options={[["yes", "Yes"], ["no", "No"], ["unsure", "Unsure"]]} onChange={v => { update("details", "previous_funding", v); if (v !== "yes") update("details", "previous_funding_details", null); }}/>{string("details", "previous_funding") === "yes" && <TextField label="Previous funding details" value={string("details", "previous_funding_details")} onChange={v => update("details", "previous_funding_details", v)} placeholder="Program or approximate amount"/>}<SelectField label="Current funding status" value={string("details", "current_funding_status")} options={OPTIONS.fundingStatus} onChange={v => update("details", "current_funding_status", v)}/><div className="sm:col-span-2"><MultiSelect label="Ownership eligibility information" hint="Optional and private. Some programs focus on underrepresented founders. You can leave this unanswered, or choose Prefer not to say." value={list("details", "ownership_eligibility")} options={OPTIONS.ownership} onChange={v => update("details", "ownership_eligibility", v)}/></div></>}
            {step === "founder_interests" && <><div className="sm:col-span-2 rounded-xl border border-emerald-100 bg-emerald-50 p-4 text-sm leading-6 text-emerald-950"><CircleHelp size={17} className="mr-2 inline"/>This section is optional. Your answers stay private. No founder directory or connection requests are active in this demo.</div><TextField label="Areas of expertise" hint="Separate areas with commas." value={list("interests", "expertise").join(",")} onChange={v => update("interests", "expertise", v ? v.split(",") : [])} placeholder="e.g. Product design, operations"/><TextField label="Biggest current challenges" hint="Separate areas with commas." value={list("interests", "challenges").join(",")} onChange={v => update("interests", "challenges", v ? v.split(",") : [])} placeholder="e.g. Sales, hiring"/><TextField label="Where would support help?" hint="Separate areas with commas." value={list("interests", "support_areas").join(",")} onChange={v => update("interests", "support_areas", v ? v.split(",") : [])} placeholder="e.g. Fundraising, marketing"/><AnswerChoice label="Interested in mentorship?" value={bool("interests", "mentorship_interest")} onChange={v => update("interests", "mentorship_interest", v)}/><AnswerChoice label="Interested in collaborating with founders?" value={bool("interests", "collaboration_interest")} onChange={v => update("interests", "collaboration_interest", v)}/><AnswerChoice label="Opt in to future founder connections?" hint="No connections are shared now. You can change this later." value={bool("interests", "connections_opt_in")} onChange={v => update("interests", "connections_opt_in", v)}/></>}
          </div>
          {error && <div role="alert" className="mb-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error} <button type="button" onClick={() => { void flush(); }} className="ml-2 font-bold underline">Retry save</button></div>}
          <div className="flex flex-wrap items-center justify-between gap-4 border-t border-slate-100 pt-6"><div role="status" className={`text-xs font-semibold ${saveState === "error" ? "text-rose-700" : "text-slate-500"}`}>{saveState === "saving" ? "Saving changes…" : saveState === "error" ? "Unable to save. Retry." : "All changes saved"}</div><div className="flex flex-wrap items-center gap-2">{index > 0 && <button type="button" onClick={() => { void go(SECTION_META[index - 1].id); }} className="inline-flex h-10 items-center gap-2 rounded-xl px-3 text-sm font-semibold text-slate-600 hover:bg-slate-100"><ArrowLeft size={16}/>Back</button>}{index > 0 && <button type="button" onClick={() => { void go(index === 4 ? "dashboard" : SECTION_META[index + 1].id, "skipped"); }} className="h-10 rounded-xl px-3 text-sm font-semibold text-slate-500 hover:bg-slate-100">Skip for now</button>}<button type="button" onClick={() => { void go(index === 4 ? "dashboard" : SECTION_META[index + 1].id, "completed"); }} className="inline-flex h-10 items-center gap-2 rounded-xl bg-emerald-800 px-5 text-sm font-semibold text-white hover:bg-emerald-900">{index === 4 ? "View dashboard" : "Continue"}<ArrowRight size={16}/></button></div></div>
        </div></main></div>
    </div>
  </div>;
}
