"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useId, useState } from "react";
import { NavBand } from "@/components/layout/NavBand";

const NAV_LINKS = [
  { href: "#", label: "TRENDS" },
  { href: "/", label: "POLICY MAP" },
  { href: "#", label: "POLICY LIST" },
] as const;

const linkClassName =
  "text-xs font-bold tracking-[0.2em] text-white hover:text-accent";

function MenuIcon({ open }: { open: boolean }) {
  if (open) {
    return (
      <svg
        width={24}
        height={24}
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden
        className="text-white"
      >
        <path
          d="M6 6l12 12M18 6L6 18"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
        />
      </svg>
    );
  }
  return (
    <svg
      width={24}
      height={24}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      className="text-white"
    >
      <path
        d="M4 7h16M4 12h16M4 17h16"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
      />
    </svg>
  );
}

export function SiteNavigation() {
  const [menuOpen, setMenuOpen] = useState(false);
  const mobileNavId = useId();

  const closeMenu = useCallback(() => setMenuOpen(false), []);

  useEffect(() => {
    if (!menuOpen) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeMenu();
    };

    document.addEventListener("keydown", onKeyDown);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = prevOverflow;
    };
  }, [menuOpen, closeMenu]);

  return (
    <header className="pt-6 lg:pt-[41px]">
      <NavBand>
        <div className="flex min-h-[76px] flex-col lg:flex-row lg:items-center lg:justify-between">
          <div className="flex w-full items-center justify-between gap-4 lg:w-auto lg:max-w-[520px] lg:justify-start">
            <div className="flex min-w-0 items-center gap-4">
              <div className="relative h-[76px] w-[62px] shrink-0">
                <Image
                  src="/brand/uic-logo.png"
                  alt=""
                  width={62}
                  height={76}
                  className="object-contain object-left"
                  priority
                />
              </div>
              <p className="font-mono text-base font-bold leading-tight tracking-tight text-white">
                URBAN INDIGENOUS COLLECTIVE
              </p>
            </div>

            <button
              type="button"
              className="flex shrink-0 items-center justify-center rounded-md p-2 text-white hover:bg-white/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent lg:hidden"
              aria-expanded={menuOpen}
              aria-controls={mobileNavId}
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              onClick={() => setMenuOpen((open) => !open)}
            >
              <MenuIcon open={menuOpen} />
            </button>
          </div>

          <nav
            className="hidden items-center gap-x-10 lg:flex lg:justify-end"
            aria-label="Primary"
          >
            {NAV_LINKS.map((item) => (
              <Link key={item.label} href={item.href} className={linkClassName}>
                {item.label}
              </Link>
            ))}
            <Link
              href="https://urbanindigenouscollective.org/donate"
              className="rounded-full bg-accent px-10 py-3.5 text-xs font-bold tracking-[0.2em] text-white hover:opacity-90"
            >
              DONATE
            </Link>
          </nav>

          {menuOpen ? (
            <nav
              id={mobileNavId}
              className="flex flex-col gap-6 border-t border-white/10 py-6 lg:hidden"
              aria-label="Primary"
            >
              {NAV_LINKS.map((item) => (
                <Link
                  key={item.label}
                  href={item.href}
                  className={linkClassName}
                  onClick={closeMenu}
                >
                  {item.label}
                </Link>
              ))}
              <Link
                href="https://urbanindigenouscollective.org/donate"
                className="inline-flex w-fit rounded-full bg-accent px-10 py-3.5 text-xs font-bold tracking-[0.2em] text-white hover:opacity-90"
                onClick={closeMenu}
              >
                DONATE
              </Link>
            </nav>
          ) : null}
        </div>
      </NavBand>
    </header>
  );
}
