import type { Metadata } from "next";

import { EmbedChromeProvider } from "@/components/embed/EmbedChromeContext";
import { ContentBand } from "@/components/layout/ContentBand";
import { ShellWidth } from "@/components/layout/ShellWidth";

export const metadata: Metadata = {
  robots: { index: false, follow: false },
  title: "MMIP Policy Tracker embed",
};

/**
 * Chrome-free shell for iframe embeds on urbanindigenouscollective.org (and peers).
 * Map embed opens bill analysis in the drawer; list embed keeps its own panel.
 */
export default function EmbedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <EmbedChromeProvider value={{ embed: true, linkTarget: "_self" }}>
      <main className="flex min-h-full flex-1 flex-col">
        <ShellWidth>
          <ContentBand>{children}</ContentBand>
        </ShellWidth>
      </main>
    </EmbedChromeProvider>
  );
}
