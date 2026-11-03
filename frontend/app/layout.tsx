import type { Metadata } from "next";
import "./globals.css";
import AiNotice from "./lib/AiNotice";

export const metadata: Metadata = {
  title: "CaseWeave AI — Incident Reconstruction Studio",
  description: "AI-powered investigation and evidence analysis platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="h-full antialiased dark">
      <body className="min-h-full flex flex-col bg-zinc-950 text-zinc-100 font-sans"><AiNotice />{children}</body>
    </html>
  );
}
