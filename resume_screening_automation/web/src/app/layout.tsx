import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Resume Screening",
  description: "AI-powered resume screening system",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-zinc-950 text-zinc-100 min-h-screen">
        <nav className="border-b border-zinc-800 px-6 py-4">
          <div className="max-w-7xl mx-auto flex items-center justify-between">
            <Link href="/" className="text-lg font-semibold tracking-tight">
              Resume Screening
            </Link>
            <div className="flex gap-6 text-sm text-zinc-400">
              <Link href="/" className="hover:text-white transition-colors">Jobs</Link>
              <Link href="/screening" className="hover:text-white transition-colors">Screen</Link>
            </div>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
