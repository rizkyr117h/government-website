import { useEffect, useState } from "react";
import Header from "@/components/Header";
import Hero from "@/components/Hero";
import ArticleFeed from "@/components/ArticleFeed";
import WorldRankings from "@/components/WorldRankings";
import ScandalTracker from "@/components/ScandalTracker";
import SocialChannels from "@/components/SocialChannels";
import Footer from "@/components/Footer";
import { api } from "@/lib/api";

export default function Home() {
  const [articles, setArticles] = useState([]);
  const [scandals, setScandals] = useState([]);
  const [rankings, setRankings] = useState([]);
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [a, s, r, c] = await Promise.all([
          api.get("/articles"),
          api.get("/scandals"),
          api.get("/rankings"),
          api.get("/channels"),
        ]);
        setArticles(a.data);
        setScandals(s.data);
        setRankings(r.data);
        setChannels(c.data);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div data-testid="home-page" className="min-h-screen bg-[#FAF8F5]">
      <Header />
      {loading ? (
        <div className="grid min-h-[60vh] place-items-center font-mono text-sm uppercase tracking-widest text-slate-500" data-testid="home-loading">
          Memuat edisi terbaru…
        </div>
      ) : (
        <main>
          <Hero article={articles[0]} scandals={scandals} />
          <ArticleFeed articles={articles} />
          <WorldRankings rankings={rankings} />
          <ScandalTracker scandals={scandals} />
          <SocialChannels channels={channels} />
        </main>
      )}
      <Footer />
    </div>
  );
}
