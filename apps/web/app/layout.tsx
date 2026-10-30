import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Seedline · Funding Discovery", description: "Discover verified funding opportunities and build your business profile" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
