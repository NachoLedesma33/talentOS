import { headers } from "next/headers";
import type { MetadataRoute } from "next";

async function baseUrl(): Promise<string> {
  const headerList = await headers();
  const host = headerList.get("host") ?? "localhost:3000";
  const proto = headerList.get("x-forwarded-proto") === "https" ? "https" : "http";
  if (!/^[a-z0-9.-]+(?::\d{1,5})?$/i.test(host)) {
    return "http://localhost:3000";
  }
  return `${proto}://${host}`;
}

export default async function robots(): Promise<MetadataRoute.Robots> {
  const origin = await baseUrl();
  return {
    rules: {
      userAgent: "*",
      allow: ["/", "/login", "/register", "/forgot-password", "/reset-password"],
      disallow: [
        "/api/",
        "/dashboard",
        "/jobs",
        "/candidates",
        "/applications",
        "/assessment",
        "/interviews",
        "/automations",
        "/agents",
        "/analytics",
        "/integrations",
        "/documents",
        "/invite/",
      ],
    },
    sitemap: `${origin}/sitemap.xml`,
  };
}
