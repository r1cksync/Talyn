import type { Metadata } from "next";
import "./globals.css";
import "@fontsource/anton/latin-400.css";
import "@fontsource/archivo/latin-400.css";
import "@fontsource/archivo/latin-600.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "./theme.css";
export const metadata: Metadata = {
  title: "Talyn — Better conversations. Clearer decisions.",
  description:
    "An evidence-led interview workspace with candidates at its center.",
  robots: { index: false, follow: false },
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
