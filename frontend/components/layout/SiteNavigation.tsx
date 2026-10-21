"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useId, useState } from "react";
import { NavBand } from "@/components/layout/NavBand";
import { DonateLink } from "@/components/ui/DonateLink";

const NAV_LINKS = [
  { href: "#", label: "TRENDS" },
  { href: "/", label: "POLICY MAP" },
  { href: "#", label: "POLICY LIST" },
] as const;

function MenuIcon({ open }: { open: boolean }) {
  if (open) {
    return (
      <svg
        width={24}
        height={24}
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden
        className="text-foreground"
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
      className="text-foreground"
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
    <header className="pt-header-top lg:pt-header-top-lg">
      <NavBand>
        <div className="flex min-h-nav-row flex-col lg:flex-row lg:items-center lg:justify-between">
          <div className="flex w-full items-center justify-between gap-nav-brand-gap lg:w-auto lg:max-w-nav-brand lg:justify-start">
            <div className="flex min-w-0 items-center gap-nav-brand-gap">
              <div className="relative h-logo w-logo shrink-0">
                <Image
                  src="/brand/uic-logo.png"
                  alt=""
                  width={62}
                  height={76}
                  className="object-contain object-left"
                  priority
                />
              </div>
              <p className="font-mono text-body font-bold leading-tight tracking-tight-ui text-foreground">
                URBAN INDIGENOUS COLLECTIVE
              </p>
            </div>

            <button
              type="button"
              className="flex shrink-0 items-center justify-center rounded-md p-2 text-foreground hover:bg-surface-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-accent lg:hidden"
              aria-expanded={menuOpen}
              aria-controls={mobileNavId}
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              onClick={() => setMenuOpen((open) => !open)}
            >
              <MenuIcon open={menuOpen} />
            </button>
          </div>

          <nav
            className="hidden items-center gap-x-nav-gap lg:flex lg:justify-end"
            aria-label="Primary"
          >
            {NAV_LINKS.map((item) => (
              <Link key={item.label} href={item.href} className="uic-nav-link">
                {item.label}
              </Link>
            ))}
            <DonateLink />
          </nav>

          {menuOpen ? (
            <nav
              id={mobileNavId}
              className="flex flex-col gap-nav-mobile-gap border-t border-surface-border py-nav-mobile-gap lg:hidden"
              aria-label="Primary"
            >
              {NAV_LINKS.map((item) => (
                <Link
                  key={item.label}
                  href={item.href}
                  className="uic-nav-link"
                  onClick={closeMenu}
                >
                  {item.label}
                </Link>
              ))}
              <DonateLink className="w-fit" onClick={closeMenu} />
            </nav>
          ) : null}
        </div>
      </NavBand>
    </header>
  );
}
