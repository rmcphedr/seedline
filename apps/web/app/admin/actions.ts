"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireAdmin } from "@/lib/admin-auth";
import { api, type EnrichmentJob, type Job, type Opportunity } from "@/lib/api";

const value = (form: FormData, key: string) => String(form.get(key) ?? "").trim();
const values = (form: FormData, key: string) => form.getAll(key).map(item => String(item).trim());
const optionalNumber = (form: FormData, key: string) => value(form, key) === "" ? null : Number(value(form, key));

function finish(path: string, message: string): never {
  revalidatePath(path);
  revalidatePath("/explore");
  redirect(`${path}?message=${encodeURIComponent(message)}`);
}

export async function createAdminOpportunity(form: FormData) {
  await requireAdmin();
  const created = await api<Opportunity>("/opportunities", { method: "POST", body: JSON.stringify({
    title: value(form, "title"), funding_type: value(form, "funding_type"),
    source_id: value(form, "source_id") || null, url: value(form, "url") || null,
    geography: value(form, "geography") || null,
  }) });
  finish(`/admin/opportunities/${created.id}`, "Opportunity added to review");
}

export async function saveOpportunityMain(form: FormData) {
  await requireAdmin();
  const id = value(form, "id");
  await api(`/opportunities/${id}`, { method: "PATCH", body: JSON.stringify({
    title: value(form, "title"), funding_type: value(form, "funding_type"),
    summary: value(form, "summary") || null, url: value(form, "url") || null,
    source_id: value(form, "source_id") || null, geography: value(form, "geography") || null,
    organization_types: values(form, "organization_types"), amount_min: optionalNumber(form, "amount_min"),
    amount_max: optionalNumber(form, "amount_max"), currency: value(form, "currency") || null,
  }) });
  finish(`/admin/opportunities/${id}`, "Details saved; verification reset");
}

export async function saveOpportunityRounds(form: FormData) {
  await requireAdmin();
  const id = value(form, "id");
  const names = values(form, "round_name");
  const statuses = values(form, "round_status");
  const opens = values(form, "round_opens_at");
  const deadlines = values(form, "round_deadline");
  const urls = values(form, "round_url");
  const removed = new Set(values(form, "remove_round"));
  const rounds = names.flatMap((name, index) => name && !removed.has(String(index)) ? [{
    name, status: statuses[index] || "unknown", opens_at: opens[index] || null, deadline: deadlines[index] || null,
    application_url: urls[index] || null,
  }] : []);
  await api(`/opportunities/${id}`, { method: "PATCH", body: JSON.stringify({ rounds }) });
  finish(`/admin/opportunities/${id}`, "Rounds saved; verification reset");
}

export async function saveOpportunityRules(form: FormData) {
  await requireAdmin();
  const id = value(form, "id");
  const criteria = values(form, "rule_criterion");
  const requirements = values(form, "rule_requirement");
  const documents = values(form, "rule_document_id");
  const urls = values(form, "rule_source_url");
  const removed = new Set(values(form, "remove_rule"));
  const eligibility_rules = criteria.flatMap((criterion, index) => criterion && !removed.has(String(index)) ? [{
    criterion, requirement: requirements[index], document_id: documents[index] || null,
    source_url: urls[index] || null,
  }] : []);
  await api(`/opportunities/${id}`, { method: "PATCH", body: JSON.stringify({ eligibility_rules }) });
  finish(`/admin/opportunities/${id}`, "Eligibility saved; verification reset");
}

export async function decideVerification(form: FormData) {
  await requireAdmin();
  const id = value(form, "id");
  const decision = value(form, "decision");
  if (decision !== "approve" && decision !== "reject") throw new Error("Invalid review decision");
  await api(`/review-queue/${value(form, "review_id")}/${decision}`, { method: "POST", body: JSON.stringify({ note: value(form, "note") || null }) });
  finish(`/admin/opportunities/${id}`, decision === "approve" ? "Opportunity verified" : "Opportunity rejected");
}

export async function setPublication(form: FormData) {
  await requireAdmin();
  const id = value(form, "id");
  const decision = value(form, "decision");
  if (decision !== "publish" && decision !== "unpublish") throw new Error("Invalid publication decision");
  await api(`/opportunities/${id}/${decision}`, { method: "POST" });
  finish(`/admin/opportunities/${id}`, decision === "publish" ? "Opportunity published" : "Opportunity unpublished");
}

export async function createAdminSource(form: FormData) {
  await requireAdmin();
  await api("/sources", { method: "POST", body: JSON.stringify({
    name: value(form, "name"), base_url: value(form, "base_url"), kind: value(form, "kind"),
    resource_type: value(form, "resource_type") || null, notes: value(form, "notes") || null,
  }) });
  finish("/admin/sources", "Source added");
}

export async function saveAdminSource(form: FormData) {
  await requireAdmin();
  await api(`/sources/${value(form, "id")}`, { method: "PATCH", body: JSON.stringify({
    name: value(form, "name"), base_url: value(form, "base_url"), kind: value(form, "kind"),
    resource_type: value(form, "resource_type") || null, notes: value(form, "notes") || null,
    active: value(form, "active") === "true",
  }) });
  finish("/admin/sources", "Source saved");
}

export async function enrichSelected(form: FormData) {
  await requireAdmin();
  const opportunity_ids = [...new Set(values(form, "opportunity_ids"))];
  if (!opportunity_ids.length) throw new Error("Select at least one opportunity");
  const jobs = await api<EnrichmentJob[]>("/api/admin/enrichment-jobs", { method: "POST", body: JSON.stringify({ opportunity_ids }) });
  const failed = jobs.filter(job => job.status === "failed").length;
  finish("/admin/opportunities", failed ? `${failed} enrichment dispatch${failed === 1 ? "" : "es"} failed; inspect the opportunity jobs` : `Started enrichment for ${jobs.length} ${jobs.length === 1 ? "opportunity" : "opportunities"}`);
}

export async function enrichOne(form: FormData) {
  await requireAdmin();
  const id = value(form, "id");
  const [job] = await api<EnrichmentJob[]>("/api/admin/enrichment-jobs", { method: "POST", body: JSON.stringify({ opportunity_ids: [id] }) });
  finish(`/admin/opportunities/${id}`, job.status === "failed" ? "Windmill dispatch failed; inspect the job below" : "Enrichment queued");
}

export async function retryEnrichment(form: FormData) {
  await requireAdmin();
  const id = value(form, "id");
  const job = await api<EnrichmentJob>(`/api/admin/enrichment-jobs/${value(form, "job_id")}/retry`, { method: "POST" });
  finish(`/admin/opportunities/${id}`, job.status === "failed" ? "Windmill retry failed; inspect the new job below" : "Enrichment retry queued");
}

export async function runAdminDiscovery(form: FormData) {
  await requireAdmin();
  const limit = value(form, "limit");
  let job: Job;
  try {
    job = await api<Job>("/api/admin/discovery-runs", { method: "POST", body: JSON.stringify({
      query: value(form, "query"), limit: limit ? Number(limit) : null, source_id: value(form, "source_id") || null,
    }) });
  } catch (error) {
    finish("/admin/discovery", error instanceof Error ? error.message : "Discovery failed");
  }
  const created = job.job_metadata?.candidates_created ?? 0;
  const skipped = job.job_metadata?.duplicates_skipped ?? 0;
  const message = job.status === "failed"
    ? (job.error || "Discovery failed")
    : `Found ${created} new ${created === 1 ? "lead" : "leads"}; skipped ${skipped} already recorded`;
  revalidatePath("/admin/discovery");
  revalidatePath("/explore");
  redirect(`/admin/discovery?job=${job.id}&message=${encodeURIComponent(message)}`);
}

export async function decideAdminCandidate(form: FormData) {
  await requireAdmin();
  const decision = value(form, "decision");
  const id = value(form, "id");
  if (decision !== "promote" && decision !== "dismiss") throw new Error("Invalid candidate decision");
  await api(`/candidates/${id}/${decision}`, {
    method: "POST",
    body: decision === "promote" ? JSON.stringify({ funding_type: value(form, "funding_type") }) : undefined,
  });
  finish("/admin/discovery", decision === "promote" ? "Lead sent to opportunity review" : "Lead dismissed");
}

export async function reviewEnrichment(form: FormData) {
  await requireAdmin();
  const id = value(form, "id");
  const jobId = value(form, "job_id");
  const decision = value(form, "decision");
  if (decision !== "approve" && decision !== "reject") throw new Error("Invalid enrichment decision");
  if (decision === "reject") {
    await api(`/api/admin/enrichment-jobs/${jobId}/reject`, { method: "POST" });
    finish(`/admin/opportunities/${id}`, "Enrichment proposal rejected");
  }
  const accepted_fields = values(form, "accepted_fields");
  const edited_fields: Record<string, unknown> = {};
  for (const field of accepted_fields) {
    const edited = value(form, `field_${field}`);
    if (edited) edited_fields[field] = JSON.parse(edited);
  }
  await api(`/api/admin/enrichment-jobs/${jobId}/approve`, {
    method: "POST", body: JSON.stringify({ accepted_fields, edited_fields }),
  });
  finish(`/admin/opportunities/${id}`, "Selected changes saved; verify before publishing");
}
