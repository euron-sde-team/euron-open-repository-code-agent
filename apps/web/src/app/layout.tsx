import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./globals.css";

import type { Metadata, Viewport } from "next";
import Script from "next/script";
import type { ReactNode } from "react";

import { Providers } from "@/lib/providers";
import { THEME_SCRIPT } from "@/lib/theme-script";

export const metadata: Metadata = {
  title: { default: "Euron CodeAgent", template: "%s | CodeAgent" },
  description:
    "A repository-aware coding assistant: code search, answers that cite your code, sandboxed test runs and reviewed patches.",
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f8f8" },
    { media: "(prefers-color-scheme: dark)", color: "#0b1012" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        <Script src="/env.js" strategy="beforeInteractive" />
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
