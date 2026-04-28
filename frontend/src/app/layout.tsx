import type { Metadata } from "next";
import { ThemeProvider } from "@/components/theme-provider";
import "./globals.css";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://megoobug.com";

export const metadata: Metadata = {
  title: {
    default: "MegooBug — Real-time Bug Tracking",
    template: "%s | MegooBug",
  },
  description:
    "Open-source, self-hosted, real-time bug tracking platform. Track errors, manage projects, and get instant notifications.",
  keywords: [
    "bug tracking",
    "error monitoring",
    "sentry alternative",
    "open source",
    "self-hosted",
    "real-time",
    "issue tracker",
  ],

  /* ── Favicon & Icons ── */
  icons: {
    icon: [
      { url: "/favicon.png", type: "image/png" },
    ],
    apple: [
      { url: "/apple-touch-icon.png", type: "image/png" },
    ],
  },

  /* ── OpenGraph ── */
  openGraph: {
    type: "website",
    siteName: "MegooBug",
    title: "MegooBug — Real-time Bug Tracking",
    description:
      "Open-source, self-hosted, real-time bug tracking platform. Track errors, manage projects, and get instant notifications.",
    url: siteUrl,
    images: [
      {
        url: `${siteUrl}/og-image.png`,
        width: 1200,
        height: 630,
        alt: "MegooBug — Real-time Bug Tracking",
      },
    ],
    locale: "en_US",
  },

  /* ── Twitter Card ── */
  twitter: {
    card: "summary_large_image",
    title: "MegooBug — Real-time Bug Tracking",
    description:
      "Open-source, self-hosted, real-time bug tracking. Track errors, manage projects, and get instant notifications.",
    images: [`${siteUrl}/og-image.png`],
  },

  /* ── Additional Meta ── */
  metadataBase: new URL(siteUrl),
  other: {
    "og:logo": `${siteUrl}/favicon.png`,
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
