import { absoluteUrl } from "@/lib/seo/site-url";

/** Same type/tracking as Donate; taller vertical pad so the longer label stays pill-shaped. */
const ctaClassName =
  "inline-flex shrink-0 items-center justify-center rounded-full bg-accent px-10 py-5 font-sans text-label-xs font-bold uppercase leading-none tracking-label text-white no-underline hover:opacity-90";

/** Opens the full tracker outside the iframe (used in the embed header row). */
export function EmbedDashboardCta() {
  return (
    <a
      href={absoluteUrl("/")}
      target="_blank"
      rel="noopener noreferrer"
      className={ctaClassName}
    >
      View full dashboard
    </a>
  );
}
