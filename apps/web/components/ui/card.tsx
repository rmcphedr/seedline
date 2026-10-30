import * as React from "react";
import { cn } from "@/lib/utils";
function Card({ className, ...props }: React.ComponentProps<"div">) { return <div className={cn("rounded-xl border border-slate-200 bg-white shadow-sm", className)} {...props} />; }
function CardHeader({ className, ...props }: React.ComponentProps<"div">) { return <div className={cn("border-b border-slate-100 px-5 py-4", className)} {...props} />; }
function CardContent({ className, ...props }: React.ComponentProps<"div">) { return <div className={cn("p-5", className)} {...props} />; }
export { Card, CardHeader, CardContent };
