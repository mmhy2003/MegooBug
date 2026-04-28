import type { Metadata } from "next";
import { ThemeProvider } from "@/components/theme-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "MegooBug — Real-time Bug Tracking",
  description:
    "Open-source, self-hosted, real-time bug tracking platform. Track errors, manage projects, and get instant notifications.",
  keywords: ["bug tracking", "error monitoring", "sentry", "open source"],
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
