import type { Metadata } from "next";
import "./globals.css";
import { SessionProvider } from "next-auth/react";
import SWRProvider from "@/components/SWRProvider";

export const metadata: Metadata = {
  title: "The Vault — Private Document Intelligence",
  description: "Self-hosted, privacy-first document vault with AI-powered semantic search. Your documents, your data.",
  keywords: ["document vault", "private AI", "OCR", "semantic search", "privacy"],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link rel="manifest" href="/manifest.json" />
        <meta name="theme-color" content="#c20114" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="apple-mobile-web-app-title" content="The Vault" />
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
      </head>
      <body>
        <SessionProvider refetchOnWindowFocus={false}>
          <SWRProvider>{children}</SWRProvider>
        </SessionProvider>
      </body>
    </html>
  );
}

