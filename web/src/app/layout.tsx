import type { Metadata, Viewport } from "next";
import { MuseoModerno, Sen } from "next/font/google";

import { Providers } from "./providers";
import "./globals.css";

const museo = MuseoModerno({ subsets: ["latin"], weight: ["500", "600"], variable: "--font-museo" });
const sen = Sen({ subsets: ["latin"], weight: ["400", "600", "700"], variable: "--font-sen" });

export const metadata: Metadata = {
  title: { default: "Forté", template: "%s · Forté" },
  description: "Payroll you can understand. Sandbox: no real money moves.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${museo.variable} ${sen.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
