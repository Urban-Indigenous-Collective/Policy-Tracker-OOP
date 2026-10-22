import Image from "next/image";
import Link from "next/link";

import { TopBorder } from "@/components/layout/TopBorder";

const UIC_ORIGIN = "https://urbanindigenouscollective.org";

const FOOTER_LINKS = {
  learnMore: UIC_ORIGIN,
  connect: `${UIC_ORIGIN}/connect`,
  about: UIC_ORIGIN,
} as const;

const SOCIAL_LINKS = [
  {
    label: "YouTube",
    href: "https://www.youtube.com/channel/UCJ9of9c5qSb7fIDsLHHTyng",
    icon: YouTubeIcon,
  },
  {
    label: "LinkedIn",
    href: "https://www.linkedin.com/company/19231105",
    icon: LinkedInIcon,
  },
  {
    label: "Instagram",
    href: "https://www.instagram.com/urbanindigenouscollective",
    icon: InstagramIcon,
  },
  {
    label: "Facebook",
    href: "https://www.facebook.com/1006248109584997",
    icon: FacebookIcon,
  },
] as const;

export function SiteFooter() {
  return (
    <footer className="mt-auto bg-footer-surface">
      <TopBorder />
      <div className="mx-auto w-full max-w-artboard px-page-x pb-footer-pb pt-footer-pt sm:px-page-x-md lg:px-content-inset lg:pr-content-gutter-right">
        <div className="flex flex-col gap-footer-mission-stack">
          <div className="flex flex-col gap-footer-mission-stack lg:flex-row lg:items-start lg:justify-between lg:gap-footer-top">
            <p className="uic-footer-mission max-w-footer-mission shrink-0">
              Serving Indigenous individuals from North, Central, and South
              America, the Caribbean, and Pacific Islands
            </p>

            <div className="relative mx-auto h-footer-logo-h w-footer-logo-w shrink-0 overflow-hidden lg:mx-0 lg:-mt-footer-logo-offset">
              <Image
                src="/brand/uic-logo.png"
                alt=""
                width={2048}
                height={2048}
                className="uic-footer-logo-img"
              />
            </div>
          </div>

          <Link href={FOOTER_LINKS.learnMore} className="uic-footer-learn">
            learn more
          </Link>
        </div>

        <hr className="my-footer-divide-y border-0 border-t border-footer-divider" />

        <div className="flex flex-col gap-footer-bottom-stack sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-footer-pill-gap">
            <Link
              href={FOOTER_LINKS.connect}
              className="uic-footer-nav-pill shrink-0 border border-footer-pill-border uppercase"
            >
              CONNECT
            </Link>
            <Link
              href={FOOTER_LINKS.about}
              className="uic-footer-nav-pill shrink-0 border border-footer-pill-border uppercase"
            >
              ABOUT US
            </Link>
          </div>

          <ul className="flex items-center gap-footer-social-gap">
            {SOCIAL_LINKS.map(({ label, href, icon: Icon }) => (
              <li key={label}>
                <Link
                  href={href}
                  className="inline-flex size-footer-social-touch items-center justify-center text-foreground transition-colors hover:text-accent"
                  aria-label={label}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Icon className="size-footer-social" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </footer>
  );
}

function YouTubeIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M23.5 6.2a3 3 0 0 0-2.1-2.1C19.5 3.5 12 3.5 12 3.5s-7.5 0-9.4.6A3 3 0 0 0 .5 6.2 31 31 0 0 0 0 12a31 31 0 0 0 .5 5.8 3 3 0 0 0 2.1 2.1c1.9.6 9.4.6 9.4.6s7.5 0 9.4-.6a3 3 0 0 0 2.1-2.1A31 31 0 0 0 24 12a31 31 0 0 0-.5-5.8ZM9.75 15.02V8.98L15.5 12l-5.75 3.02Z" />
    </svg>
  );
}

function LinkedInIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M20.45 20.45h-3.56v-5.57c0-1.33-.03-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.95v5.66H9.34V9h3.42v1.56h.05c.47-.9 1.63-1.85 3.36-1.85 3.6 0 4.26 2.37 4.26 5.45v6.29ZM5.34 7.43a2.06 2.06 0 1 1 0-4.12 2.06 2.06 0 0 1 0 4.12Zm1.78 13.02H3.56V9h3.56v11.45ZM22.22 0H1.77C.79 0 0 .77 0 1.72v20.56C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.72V1.72C24 .77 23.2 0 22.22 0Z" />
    </svg>
  );
}

function InstagramIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2.16c3.2 0 3.58.01 4.85.07 1.17.05 1.8.25 2.23.41.56.22.96.48 1.38.9.42.42.68.82.9 1.38.16.43.36 1.06.41 2.23.06 1.27.07 1.65.07 4.85s-.01 3.58-.07 4.85c-.05 1.17-.25 1.8-.41 2.23-.22.56-.48.96-.9 1.38-.42.42-.82.68-1.38.9-.43.16-1.06.36-2.23.41-1.27.06-1.65.07-4.85.07s-3.58-.01-4.85-.07c-1.17-.05-1.8-.25-2.23-.41a3.7 3.7 0 0 1-1.38-.9 3.7 3.7 0 0 1-.9-1.38c-.16-.43-.36-1.06-.41-2.23C2.17 15.58 2.16 15.2 2.16 12s.01-3.58.07-4.85c.05-1.17.25-1.8.41-2.23.22-.56.48-.96.9-1.38.42-.42.82-.68 1.38-.9.43-.16 1.06-.36 2.23-.41C8.42 2.17 8.8 2.16 12 2.16ZM12 0C8.74 0 8.33.01 7.05.07 5.78.13 4.9.33 4.15.63a5.9 5.9 0 0 0-2.13 1.38A5.9 5.9 0 0 0 .63 4.15C.33 4.9.13 5.78.07 7.05.01 8.33 0 8.74 0 12s.01 3.67.07 4.95c.06 1.27.26 2.15.56 2.9a5.9 5.9 0 0 0 1.39 2.13 5.9 5.9 0 0 0 2.13 1.39c.75.3 1.63.5 2.9.56C8.33 23.99 8.74 24 12 24s3.67-.01 4.95-.07c1.27-.06 2.15-.26 2.9-.56a5.9 5.9 0 0 0 2.13-1.39 5.9 5.9 0 0 0 1.39-2.13c.3-.75.5-1.63.56-2.9.06-1.28.07-1.67.07-4.95s-.01-3.67-.07-4.95c-.06-1.27-.26-2.15-.56-2.9a5.9 5.9 0 0 0-1.39-2.13A5.9 5.9 0 0 0 19.85.63C19.1.33 18.22.13 16.95.07 15.67.01 15.26 0 12 0Zm0 5.84A6.16 6.16 0 1 0 18.16 12 6.16 6.16 0 0 0 12 5.84Zm0 10.16A4 4 0 1 1 16 12a4 4 0 0 1-4 4Zm6.41-10.55a1.44 1.44 0 1 0-1.44 1.44 1.44 1.44 0 0 0 1.44-1.44Z" />
    </svg>
  );
}

function FacebookIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M24 12.07C24 5.41 18.63 0 12 0S0 5.41 0 12.07c0 6.03 4.39 11.03 10.13 11.93v-8.44H7.08v-3.5h3.05V9.41c0-3.02 1.79-4.69 4.53-4.69 1.31 0 2.68.23 2.68.23v2.96h-1.51c-1.49 0-1.95.93-1.95 1.88v2.26h3.32l-.53 3.5h-2.79v8.44C19.61 23.1 24 18.1 24 12.07Z" />
    </svg>
  );
}
