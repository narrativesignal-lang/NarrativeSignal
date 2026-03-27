import "./globals.css";

import type { Metadata } from "next";

import { I18nProvider } from "@/lib/i18n";
import { UserProvider } from "@/lib/UserContext";

export const metadata: Metadata = {
  title: "Narrative Investing Dashboard",
  description: "AI narrative & sentiment monitoring"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-slate-950 text-slate-50">
        <I18nProvider>
          <UserProvider>
            <div className="min-h-screen">{children}</div>
          </UserProvider>
        </I18nProvider>
      </body>
    </html>
  );
}

