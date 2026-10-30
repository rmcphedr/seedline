import { notFound } from "next/navigation";
import { DemoStart } from "@/components/demo-start";
import { demoEnabled } from "@/lib/demo-server";

export const dynamic = "force-dynamic";
export default function DemoPage() {
  if (!demoEnabled()) notFound();
  return <DemoStart/>;
}
