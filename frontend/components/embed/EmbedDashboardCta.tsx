"use client";

import { trackCtaClick } from "@/lib/analytics/events";
import { absoluteUrl } from "@/lib/seo/site-url";

/** Match Donate pill proportions; short label so it doesn’t dominate the map. */
const ctaClassName =
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-full bg-accent px-10 py-3.5 font-sans text-label-xs font-bold uppercase leading-none tracking-label text-white no-underline hover:opacity-90";

function ExternalArrowIcon() {
  return (
    <svg
      width={12}
      height={12}
      viewBox="0 0 12 12"
      fill="none"
      aria-hidden
      className="shrink-0"
    >
      <path
        d="M3.5 2H10v6.5M10 2 2 10"
        stroke="currentColor"
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Opens the full tracker outside the iframe (embed header, right of stats). */
export function EmbedDashboardCta() {
  const href = absoluteUrl("/");
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={ctaClassName}
      onClick={() =>
        trackCtaClick({
          ctaId: "embed_dashboard",
          label: "Dashboard",
          url: href,
        })
      }
    >
      Dashboard
      <ExternalArrowIcon />
    </a>
  );
}
