import { ContentBand } from "@/components/layout/ContentBand";
import { SiteNavigation } from "@/components/layout/SiteNavigation";
import { ShellWidth } from "@/components/layout/ShellWidth";
import { TopBorder } from "@/components/layout/TopBorder";
import { DevHealthBanner } from "@/components/dev/DevHealthBanner";

export function SiteShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <TopBorder />
      <ShellWidth>
        <SiteNavigation />
      </ShellWidth>
      <main className="flex-1 pb-16 pt-2 lg:pt-4">
        <ShellWidth>
          <ContentBand>{children}</ContentBand>
        </ShellWidth>
      </main>
      <DevHealthBanner />
    </>
  );
}
