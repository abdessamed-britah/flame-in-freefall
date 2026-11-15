import type { Metadata } from "next";
import AskArchive from "@/components/AskArchive";
import Nav from "@/components/Nav";
import { AudienceProvider } from "@/lib/audience";
import { STREAMLIT_URL } from "@/lib/config";
import "./globals.css";

export const metadata: Metadata = {
  title: "Flame in Freefall",
  description: "What NASA's microgravity combustion tests say about fire safety in a Moon Base.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <AudienceProvider>
          <Nav />
          <main className="mx-auto w-full min-w-0 max-w-6xl flex-1 px-4 py-8">{children}</main>
          <footer className="border-t border-line px-4 pt-4 pb-20 text-center text-xs text-muted">
            Data: NASA Physical Sciences Informatics (PSI), CC0. AI text is always labelled. Every number is exported
            once from the team&apos;s Python code; nothing is predicted in the browser.{" "}
            Live app with AI questions: <a href={STREAMLIT_URL}>{STREAMLIT_URL.replace(/^https:\/\//, "").replace(/\/$/, "")}</a>.
          </footer>
          <AskArchive />
        </AudienceProvider>
      </body>
    </html>
  );
}
