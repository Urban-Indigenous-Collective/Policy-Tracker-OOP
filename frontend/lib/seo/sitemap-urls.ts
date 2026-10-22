import { fetchPublicSitemap } from "@/lib/api/client";
import { absoluteUrl } from "@/lib/seo/site-url";

export type SitemapEntry = {
  url: string;
  lastModified?: Date;
};

/** All indexable public routes from Flask snapshot (`GET /api/v1/sitemap`). */
export async function collectPublicSitemapEntries(): Promise<SitemapEntry[]> {
  try {
    const payload = await fetchPublicSitemap({ base: "server" });
    const lastModified = payload.generatedAt
      ? new Date(payload.generatedAt)
      : undefined;
    return payload.paths.map((path) => ({
      url: absoluteUrl(path),
      lastModified,
    }));
  } catch {
    return [{ url: absoluteUrl("/") }];
  }
}
