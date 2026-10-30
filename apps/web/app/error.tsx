"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function ErrorPage({ error, reset }: { error: Error; reset: () => void }) {
  return <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-6"><div className="mb-3 text-xs font-semibold uppercase tracking-widest text-indigo-600">Bridge admin</div><h1 className="text-3xl font-semibold text-slate-900">This action could not be completed</h1><p className="mt-3 text-sm leading-6 text-slate-600">{error.message}</p><div className="mt-6 flex gap-3"><Button onClick={reset}>Try again</Button><Button asChild variant="outline"><Link href="/">Dashboard</Link></Button></div></main>;
}
