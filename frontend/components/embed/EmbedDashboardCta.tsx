import { absoluteUrl } from "@/lib/seo/site-url";

/** Same type/tracking as Donate; taller vertical pad so the longer label stays pill-shaped. */
const ctaClassName =
  "inline-flex shrink-0 items-center justify-center rounded-full bg-accent px-10 py-5 font-sans text-label-xs font-bold uppercase leading-none tracking-label text-white no-underline hover:opacity-90";

/** Centered CTA under the map embed — opens the full tracker outside the iframe. */
export function EmbedDashboardCta() {
  return (
    <div className="mt-[150px] flex justify-center pb-8">
      <a
        href={absoluteUrl("/")}
        target="_blank"
        rel="noopener noreferrer"
        className={ctaClassName}
      >
        View full dashboard
      </a>
    </div>
  );
}
