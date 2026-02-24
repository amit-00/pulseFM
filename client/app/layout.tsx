import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { Analytics } from "@vercel/analytics/next";
import { SpeedInsights } from "@vercel/speed-insights/next";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  applicationName: "pulseFM",
  title: {
    default: "pulseFM",
    template: "%s | pulseFM",
  },
  description:
    "PulseFM is a 24/7 Lofi AI radio station streaming continuous chill beats.",
  keywords: [
    "pulseFM",
    "24/7 lofi",
    "lofi radio",
    "AI radio station",
    "chill beats",
    "live stream",
  ],
  alternates: {
    canonical: "/",
  },
  openGraph: {
    type: "website",
    url: "/",
    siteName: "pulseFM",
    title: "pulseFM - 24/7 Lofi AI Radio Station",
    description:
      "PulseFM is a 24/7 Lofi AI radio station streaming continuous chill beats.",
  },
  twitter: {
    card: "summary",
    title: "pulseFM - 24/7 Lofi AI Radio Station",
    description:
      "PulseFM is a 24/7 Lofi AI radio station streaming continuous chill beats.",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="bg-stone-950">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-stone-950`}
      >
        {children}
        <Analytics />
        <SpeedInsights />
      </body>
    </html>
  );
}
