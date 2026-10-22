import type { MetadataRoute } from "next";

import { collectPublicSitemapEntries } from "@/lib/seo/sitemap-urls";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const entries = await collectPublicSitemapEntries();
  return entries.map(({ url, lastModified }) => ({
    url,
    lastModified,
    changeFrequency: "weekly" as const,
    priority: url.endsWith("/") ? 1 : url.includes("/bills/") ? 0.8 : 0.9,
  }));
}
