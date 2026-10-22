import type { Metadata } from "next";
import { Montserrat, Roboto, Roboto_Mono } from "next/font/google";
import "./globals.css";
import { SiteShell } from "@/components/layout/SiteShell";
import { QueryProvider } from "@/components/providers/QueryProvider";
import { getSiteUrl } from "@/lib/seo/site-url";

const montserrat = Montserrat({
  variable: "--font-montserrat",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  display: "swap",
});

const roboto = Roboto({
  variable: "--font-roboto-family",
  subsets: ["latin"],
  weight: ["600"],
  display: "swap",
});

const robotoMono = Roboto_Mono({
  variable: "--font-roboto-mono",
  subsets: ["latin"],
  weight: ["600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: getSiteUrl(),
  title: {
    default: "MMIP Policy Tracker | Urban Indigenous Collective",
    template: "%s | MMIP Policy Tracker",
  },
  description:
    "Interactive map of U.S. state MMIP legislation and UIC policy analysis — Missing and Murdered Indigenous Women, Girls, Trans, and Two-Spirit relatives (MMIWGT2S).",
  openGraph: {
    type: "website",
    locale: "en_US",
    siteName: "MMIP Policy Tracker",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${montserrat.variable} ${roboto.variable} ${robotoMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col bg-background text-foreground">
        <QueryProvider>
          <SiteShell>{children}</SiteShell>
        </QueryProvider>
      </body>
    </html>
  );
}
