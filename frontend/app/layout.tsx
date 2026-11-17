import type { Metadata } from "next";
import { GoogleTagManager } from "@next/third-parties/google";
import localFont from "next/font/local";
import "./globals.css";
import { QueryProvider } from "@/components/providers/QueryProvider";
import { getSiteUrl } from "@/lib/seo/site-url";

/** GTM container (loads GA4 and other tags configured in Tag Manager). */
const gtmId = process.env.NEXT_PUBLIC_GTM_ID?.trim() || "";

/**
 * Self-hosted latin files (same families/weights as former next/font/google).
 * Avoids Next 16 Turbopack CI flakes when Google returns extensionless /l/font?kit= URLs
 * (vercel/next.js#99114).
 */
const montserrat = localFont({
  src: "./fonts/montserrat-latin-var.woff2",
  variable: "--font-montserrat",
  weight: "300 700",
  display: "swap",
});

const roboto = localFont({
  src: "./fonts/roboto-latin-600.woff2",
  variable: "--font-roboto-family",
  weight: "600",
  display: "swap",
});

const robotoMono = localFont({
  src: "./fonts/roboto-mono-latin-var.woff2",
  variable: "--font-roboto-mono",
  weight: "600 700",
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
        {gtmId ? <GoogleTagManager gtmId={gtmId} /> : null}
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
