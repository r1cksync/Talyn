import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Talyn — Better conversations. Clearer decisions.', description: 'An evidence-led interview workspace with candidates at its center.', robots: { index: false, follow: false } };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body><a href="#main" className="skip-link">Skip to content</a>{children}</body></html>; }
