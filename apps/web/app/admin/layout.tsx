import Link from "next/link";
import { Compass, Database, Layers3, LayoutDashboard, Search, ShieldCheck } from "lucide-react";
import { requireAdmin } from "@/lib/admin-auth";

const nav = [
  { href: "/admin/opportunities", label: "Opportunities", icon: LayoutDashboard },
  { href: "/admin/discovery", label: "Discovery", icon: Search },
  { href: "/admin/sources", label: "Funding sources", icon: Database },
  { href: "/", label: "Ingestion & review", icon: Layers3 },
  { href: "/explore", label: "Public explorer", icon: Compass },
];

export default async function AdminLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  await requireAdmin();
  return <div className="min-h-screen bg-[#f5f8f7] lg:flex"><aside className="border-b border-slate-200 bg-slate-950 text-white lg:sticky lg:top-0 lg:h-screen lg:w-64 lg:shrink-0 lg:border-b-0"><div className="border-b border-white/10 px-6 py-6"><Link href="/admin/opportunities" className="text-2xl font-bold tracking-tight">bridge<span className="text-teal-300">.</span></Link><p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-400">Funding administration</p></div><nav className="flex gap-1 overflow-x-auto p-3 lg:block lg:space-y-1" aria-label="Admin navigation">{nav.map(({ href, label, icon: Icon }) => <Link key={href} href={href} className="flex shrink-0 items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium text-slate-300 transition hover:bg-white/10 hover:text-white"><Icon size={18} aria-hidden="true" />{label}</Link>)}</nav><div className="hidden px-6 pt-8 text-xs leading-5 text-slate-400 lg:block"><ShieldCheck size={18} className="mb-2 text-teal-300" aria-hidden="true" />Verification and publication are separate decisions.</div></aside><div className="min-w-0 flex-1">{children}</div></div>;
}
