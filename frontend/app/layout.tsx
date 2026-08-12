import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BookTranslate AI",
  description: "AI-powered platform for technical book translation",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
