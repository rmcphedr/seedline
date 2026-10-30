"use client";

import { useFormStatus } from "react-dom";

export function DiscoverySubmit() {
  const { pending } = useFormStatus();
  return (
    <button
      disabled={pending}
      className="w-full rounded-xl bg-teal-800 px-4 py-3 text-sm font-semibold text-white hover:bg-teal-900 disabled:cursor-wait disabled:bg-slate-400"
    >
      {pending ? "Searching the web…" : "Run discovery"}
    </button>
  );
}
