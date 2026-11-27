import type { Metadata } from "next";
import type { ReactNode } from "react";
import { LocaleProvider } from "../lib/i18n";
import "./globals.css";

const siteUrl = process.env.NEXT_PUBLIC_WEB_BASE_URL ?? "http://localhost:3000";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "TalentOS",
    template: "%s · TalentOS",
  },
  applicationName: "TalentOS",
  description: "Reclutamiento asistido, trazable y supervisado.",
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    url: "/",
    siteName: "TalentOS",
    title: "TalentOS",
    description: "Decisiones de contratación con evidencia, no con corazonadas.",
    locale: "es_ES",
  },
  twitter: {
    card: "summary",
    title: "TalentOS",
    description: "Reclutamiento asistido, trazable y supervisado.",
  },
  robots: { index: true, follow: true },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      name: "TalentOS",
      url: siteUrl,
      description: "Reclutamiento asistido, trazable y supervisado.",
    },
    {
      "@type": "SoftwareApplication",
      name: "TalentOS",
      applicationCategory: "BusinessApplication",
      operatingSystem: "Web",
      description: "Decisiones de contratación con evidencia, no con corazonadas.",
      url: siteUrl,
      offers: { "@type": "Offer", price: "0", priceCurrency: "EUR" },
    },
  ],
};

const structuredData = JSON.stringify(jsonLd).replace(/</g, "\\u003c");

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="es">
      <body className="paper-texture min-h-screen bg-surface font-sans text-text antialiased">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: structuredData }}
        />
        <LocaleProvider>
          <a
            href="#main-content"
            className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-sm focus:bg-surface focus:px-3 focus:py-2 focus:text-sm focus:font-semibold"
          >
            Saltar al contenido principal
          </a>
          <main
            id="main-content"
            tabIndex={-1}
            className="mx-auto w-full max-w-[1440px] px-4 py-8 sm:px-6 lg:px-10"
          >
            {children}
          </main>
        </LocaleProvider>
      </body>
    </html>
  );
}
