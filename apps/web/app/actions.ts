"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { api } from "@/lib/api";
import { requireAdmin } from "@/lib/admin-auth";

function value(form: FormData, key: string) { return String(form.get(key) ?? "").trim(); }
function done(section: string, message: string): never { revalidatePath("/"); redirect(`/?view=${section}&message=${encodeURIComponent(message)}`); }

export async function createSource(form: FormData) {
  await requireAdmin();
  await api("/sources", { method: "POST", body: JSON.stringify({ name: value(form, "name"), base_url: value(form, "base_url"), kind: value(form, "kind") }) });
  done("sources", "Source added");
}

export async function toggleSource(form: FormData) {
  await requireAdmin();
  await api(`/sources/${value(form, "id")}`, { method: "PATCH", body: JSON.stringify({ active: value(form, "active") === "true" }) });
  done("sources", "Source updated");
}

export async function deleteSource(form: FormData) {
  await requireAdmin();
  await api(`/sources/${value(form, "id")}`, { method: "DELETE" });
  done("sources", "Source deleted");
}

export async function createOpportunity(form: FormData) {
  await requireAdmin();
  const deadline = value(form, "deadline");
  const source = value(form, "source_id");
  await api("/opportunities", { method: "POST", body: JSON.stringify({
    title: value(form, "title"), funding_type: value(form, "funding_type"), summary: value(form, "summary") || null,
    url: value(form, "url") || null, geography: value(form, "geography") || null, source_id: source || null,
    rounds: deadline ? [{ name: "Current round", status: "open", deadline: new Date(deadline).toISOString() }] : []
  }) });
  done("opportunities", "Opportunity submitted for review");
}

export async function createJob(form: FormData) {
  await requireAdmin();
  await api("/ingestion-jobs", { method: "POST", body: JSON.stringify({
    source_id: value(form, "source_id") || null,
    mode: value(form, "mode"), query: value(form, "query"), limit: Number(value(form, "limit") || 8)
  }) });
  done("ingestion", "Job recorded as queued");
}

export async function decideCandidate(form: FormData) {
  await requireAdmin();
  const decision = value(form, "decision");
  const id = value(form, "id");
  await api(`/candidates/${id}/${decision}`, {
    method: "POST",
    body: decision === "promote" ? JSON.stringify({ funding_type: value(form, "funding_type") }) : undefined
  });
  done("discovery", decision === "promote" ? "Candidate sent to opportunity review" : "Candidate dismissed");
}

export async function decideReview(form: FormData) {
  await requireAdmin();
  const decision = value(form, "decision");
  await api(`/review-queue/${value(form, "id")}/${decision}`, { method: "POST", body: JSON.stringify({ note: value(form, "note") || null }) });
  done("review", `Opportunity ${decision === "approve" ? "approved" : "rejected"}`);
}
