"use client";

import Link from "next/link";

import { trackCtaClick } from "@/lib/analytics/events";

const UIC_ORIGIN = "https://urbanindigenouscollective.org";

export const FOOTER_LINKS = {
  connect: `${UIC_ORIGIN}/connect`,
  about: UIC_ORIGIN,
} as const;

export const SOCIAL_LINKS = [
  {
    label: "YouTube",
    href: "https://www.youtube.com/channel/UCJ9of9c5qSb7fIDsLHHTyng",
  },
  {
    label: "LinkedIn",
    href: "https://www.linkedin.com/company/19231105",
  },
  {
    label: "Instagram",
    href: "https://www.instagram.com/urbanindigenouscollective",
  },
  {
    label: "Facebook",
    href: "https://www.facebook.com/1006248109584997",
  },
] as const;

export function FooterNavPills() {
  return (
    <div className="flex flex-wrap gap-footer-pill-gap">
      <Link
        href={FOOTER_LINKS.connect}
        className="uic-footer-nav-pill shrink-0 border border-footer-pill-border uppercase"
        onClick={() =>
          trackCtaClick({
            ctaId: "footer_connect",
            label: "CONNECT",
            url: FOOTER_LINKS.connect,
          })
        }
      >
        CONNECT
      </Link>
      <Link
        href={FOOTER_LINKS.about}
        className="uic-footer-nav-pill shrink-0 border border-footer-pill-border uppercase"
        onClick={() =>
          trackCtaClick({
            ctaId: "footer_about",
            label: "ABOUT US",
            url: FOOTER_LINKS.about,
          })
        }
      >
        ABOUT US
      </Link>
    </div>
  );
}

export function FooterSocialLinks({
  icons,
}: {
  icons: Record<
    (typeof SOCIAL_LINKS)[number]["label"],
    React.ComponentType<{ className?: string }>
  >;
}) {
  return (
    <ul className="flex items-center gap-footer-social-gap">
      {SOCIAL_LINKS.map(({ label, href }) => {
        const Icon = icons[label];
        return (
          <li key={label}>
            <Link
              href={href}
              className="inline-flex size-footer-social-touch items-center justify-center text-foreground transition-colors hover:text-accent"
              aria-label={label}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() =>
                trackCtaClick({
                  ctaId: "footer_social",
                  label,
                  url: href,
                })
              }
            >
              <Icon className="size-footer-social" aria-hidden />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
