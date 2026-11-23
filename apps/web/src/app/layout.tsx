import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "TalentOS",
  description: "Reclutamiento asistido, trazable y supervisado.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="es">
      <body className="min-h-screen bg-surface font-sans text-text antialiased">
        <header className="border-b border-border bg-surface">
          <div className="mx-auto flex max-w-4xl items-center px-4 py-4">
            <span className="text-sm font-semibold tracking-tight">TalentOS</span>
          </div>
        </header>
        <main className="mx-auto w-full max-w-4xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
