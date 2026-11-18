import Image from "next/image";

import {
  FooterNavPills,
  FooterSocialLinks,
} from "@/components/layout/FooterTrackedLinks";
import { TopBorder } from "@/components/layout/TopBorder";
import { MonthlyDigestSignup } from "@/components/subscribe/MonthlyDigestSignup";

function FooterLogo() {
  return (
    <div className="relative mx-auto h-footer-logo-h w-footer-logo-w shrink-0 overflow-hidden lg:mx-0 lg:-mt-footer-logo-offset">
      <Image
        src="/brand/uic-logo.png"
        alt=""
        width={2048}
        height={2048}
        className="uic-footer-logo-img"
      />
    </div>
  );
}

export function SiteFooter() {
  return (
    <footer id="subscribe" className="mt-auto scroll-mt-4 bg-footer-surface">
      <TopBorder />
      <div className="mx-auto w-full max-w-artboard px-page-x pb-footer-pb pt-footer-pt sm:px-page-x-md lg:px-content-inset lg:pr-content-gutter-right">
        <MonthlyDigestSignup logo={<FooterLogo />} />

        <hr className="my-footer-divide-y border-0 border-t border-footer-divider" />

        <div className="flex flex-col gap-footer-bottom-stack sm:flex-row sm:items-center sm:justify-between">
          <FooterNavPills />
          <FooterSocialLinks />
        </div>
      </div>
    </footer>
  );
}
