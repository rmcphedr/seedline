import { Search } from "lucide-react";

export type FilterParams = { search?: string; funding_type?: string; geography?: string; organization_type?: string; application_status?: string; review_status?: string; publication_status?: string };
const field = "h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 focus:border-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-100";

export function OpportunityFilters({ params, admin = false }: { params: FilterParams; admin?: boolean }) {
  return <form action={admin ? "/admin/opportunities" : "/explore"} className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-2 xl:grid-cols-6">
    <label className="relative xl:col-span-2"><span className="sr-only">Search opportunities</span><Search size={17} className="absolute left-3 top-3.5 text-slate-400" aria-hidden="true" /><input className={`${field} pl-10`} name="search" placeholder="Search opportunities" defaultValue={params.search || ""}/></label>
    <label><span className="sr-only">Funding type</span><select className={field} name="funding_type" defaultValue={params.funding_type || ""}><option value="">All funding types</option>{["grant", "loan", "investment", "procurement", "competition"].map(type => <option key={type} value={type}>{type[0].toUpperCase() + type.slice(1)}</option>)}</select></label>
    <label><span className="sr-only">Geography</span><input className={field} name="geography" defaultValue={params.geography || ""} placeholder="Any geography" /></label>
    <label><span className="sr-only">Organization type</span><select className={field} name="organization_type" defaultValue={params.organization_type || ""}><option value="">All applicants</option><option value="business">Business</option><option value="nonprofit">Nonprofit</option><option value="individual">Individual</option><option value="cooperative">Cooperative</option></select></label>
    <label><span className="sr-only">Application status</span><select className={field} name="application_status" defaultValue={params.application_status || ""}><option value="">Any intake status</option><option value="open">Open</option><option value="upcoming">Upcoming</option><option value="closed">Closed</option><option value="unknown">Unconfirmed</option></select></label>
    {admin && <><label><span className="sr-only">Verification status</span><select className={field} name="review_status" defaultValue={params.review_status || ""}><option value="">Any verification</option><option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option></select></label><label><span className="sr-only">Publication status</span><select className={field} name="publication_status" defaultValue={params.publication_status || ""}><option value="">Any publication</option><option value="published">Published</option><option value="unpublished">Unpublished</option></select></label></>}
    <button className="h-11 rounded-xl bg-teal-800 px-5 text-sm font-semibold text-white hover:bg-teal-900">Apply filters</button>
  </form>;
}
