import { headers } from "next/headers";
import type { MetadataRoute } from "next";

const publicPaths = ["/", "/login", "/register", "/forgot-password", "/reset-password"];

async function baseUrl(): Promise<string> {
  const headerList = await headers();
  const host = headerList.get("host") ?? "localhost:3000";
  const proto = headerList.get("x-forwarded-proto") === "https" ? "https" : "http";
  if (!/^[a-z0-9.-]+(?::\d{1,5})?$/i.test(host)) {
    return "http://localhost:3000";
  }
  return `${proto}://${host}`;
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const origin = await baseUrl();
  return publicPaths.map((path) => ({
    url: `${origin}${path}`,
    changeFrequency: path === "/" ? "weekly" : "monthly",
    priority: path === "/" ? 1 : 0.6,
  }));
}
