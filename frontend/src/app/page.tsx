import type { Metadata } from "next";
import HomeClient from "./HomeClient";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL || "https://narrative-investing.example.com";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Narrative Investing — AI Narrative Intelligence for Markets",
    template: "%s | Narrative Investing",
  },
  description:
    "AI-powered narrative and sentiment monitoring for markets. Track sentiment, monitor narratives, and surface signals across entities and themes. Built for researchers and investors who think in storylines. Alternative data, news sentiment, thematic investing, quantitative finance.",
  keywords: [
    "Narrative Investing",
    "AI narrative intelligence",
    "sentiment analysis",
    "market sentiment",
    "LLM finance",
    "quantitative finance",
    "thematic investing",
    "alternative data",
    "news sentiment",
    "NLP finance",
    "alpha generation",
    "regime detection",
    "market trends",
    "narrative finance",
    "machine learning investing",
    "sentiment tracking",
    "entity monitoring",
    "theme research",
  ],
  authors: [{ name: "Narrative Investing" }],
  creator: "Narrative Investing",
  openGraph: {
    type: "website",
    locale: "en_US",
    url: SITE_URL,
    siteName: "Narrative Investing",
    title: "Narrative Investing — AI Narrative Intelligence for Markets",
    description:
      "AI-powered narrative and sentiment monitoring. Track sentiment, monitor narratives, surface signals. Built for researchers and investors.",
    images: [],
  },
  twitter: {
    card: "summary_large_image",
    title: "Narrative Investing — AI Narrative Intelligence for Markets",
    description: "AI-powered narrative and sentiment monitoring for markets.",
  },
  robots: {
    index: true,
    follow: true,
  },
  alternates: {
    canonical: SITE_URL,
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "WebApplication",
  name: "Narrative Investing",
  description:
    "AI-powered narrative and sentiment monitoring for markets. Track sentiment, monitor narratives, and surface signals across entities and themes. Built for researchers and investors who think in storylines.",
  url: SITE_URL,
  applicationCategory: "FinanceApplication",
  offers: { "@type": "Offer", price: "0" },
  featureList: [
    "Narrative tracking",
    "Sentiment analysis",
    "Cross Comparison",
    "Monitoring reports",
    "Skills Community",
    "Alternative data",
    "Target monitoring",
  ],
};

export default function HomePage() {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <HomeClient />
    </>
  );
}
