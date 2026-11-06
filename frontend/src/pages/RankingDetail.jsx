import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowLeft, ExternalLink, TrendingUp, TrendingDown, Minus } from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import { api } from "@/lib/api";

const TREND_META = {
  naik: { icon: TrendingUp, label: "Membaik", cls: "text-emerald-400 border-emerald-500" },
  turun: { icon: TrendingDown, label: "Memburuk", cls: "text-red-400 border-red-500" },
  stagnan: { icon: Minus, label: "Stagnan", cls: "text-slate-400 border-slate-500" },
};

export default function RankingDetail() {
  const { key } = useParams();
  const [ranking, setRanking] = useState(null);
  const [others, setOthers] = useState([]);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/rankings/${key}`);
        setRanking(data);
        const all = await api.get("/rankings");
        setOthers(all.data.filter((r) => r.key !== key).slice(0, 4));
      } catch {
        setNotFound(true);
      }
    })();
  }, [key]);

  if (notFound) {
    return (
      <div className="min-h-screen bg-[#FAF8F5]">
        <Header />
        <div className="grid min-h-[50vh] place-items-center font-mono text-sm uppercase tracking-widest text-slate-500" data-testid="ranking-not-found">
          Indeks tidak ditemukan.
        </div>
        <Footer />
      </div>
    );
  }

  if (!ranking) {
    return (
      <div className="min-h-screen bg-[#FAF8F5]">
        <Header />
        <div className="grid min-h-[50vh] place-items-center font-mono text-sm uppercase tracking-widest text-slate-500">
          Memuat data indeks…
        </div>
        <Footer />
      </div>
    );
  }

  const trend = TREND_META[ranking.trend] || TREND_META.stagnan;
  const TrendIcon = trend.icon;

  return (
    <div className="min-h-screen bg-[#FAF8F5]" data-testid="ranking-detail-page">
      <Header />
      <main>
        <section className="border-b-2 border-slate-900 bg-slate-900 py-12 text-white">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
            <Link
              to="/#peringkat"
              data-testid="ranking-back-link"
              className="inline-flex items-center gap-2 text-xs font-mono font-semibold uppercase tracking-wider text-slate-400 transition-colors hover:text-red-400"
            >
              <ArrowLeft size={14} /> Semua Indeks
            </Link>
            <div className="mt-8 grid grid-cols-1 gap-10 lg:grid-cols-12">
              <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.55 }} className="lg:col-span-5">
                <p className="text-xs font-mono font-semibold uppercase tracking-[0.2em] text-red-400">Indonesia vs Dunia</p>
                <h1 className="mt-2 font-serif text-3xl font-extrabold leading-tight sm:text-4xl lg:text-5xl" data-testid="ranking-label">
                  {ranking.label}
                </h1>
                <div className="mt-8 flex items-end gap-6">
                  <p className="font-serif text-6xl font-black text-white sm:text-7xl" data-testid="ranking-value">
                    {ranking.value}
                  </p>
                  <div className="pb-2">
                    <p className="font-mono text-sm font-bold text-red-400" data-testid="ranking-rank">
                      #{ranking.rank}
                    </p>
                    <p className="text-xs font-mono text-slate-400">dari {ranking.total} negara</p>
                  </div>
                </div>
                <div className="mt-6 h-2 w-full max-w-md bg-slate-700">
                  <div className="h-full bg-red-600" style={{ width: `${ranking.pct}%` }} />
                </div>
                <span className={`mt-5 inline-flex items-center gap-2 border px-3 py-1.5 text-xs font-mono font-bold uppercase tracking-wider ${trend.cls}`} data-testid="ranking-trend-badge">
                  <TrendIcon size={14} /> Tren: {trend.label}
                </span>
                <p className="mt-6 max-w-md text-sm leading-relaxed text-slate-300" data-testid="ranking-note">
                  {ranking.note}
                </p>
                {ranking.source_url && (
                  <a
                    href={ranking.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    data-testid="ranking-source-link"
                    className="mt-6 inline-flex items-center gap-2 border-2 border-white px-5 py-2.5 text-xs font-bold uppercase tracking-wider text-white transition-colors hover:border-red-500 hover:bg-red-600"
                  >
                    <ExternalLink size={14} /> Sumber: {ranking.source}
                  </a>
                )}
              </motion.div>

              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.55, delay: 0.15 }}
                className="lg:col-span-7"
              >
                <div className="border border-slate-700 bg-white p-5 sm:p-6" data-testid="ranking-chart">
                  <div className="mb-4 flex items-center justify-between">
                    <p className="text-xs font-mono font-bold uppercase tracking-[0.2em] text-slate-500">Tren Tahunan</p>
                    <p className="text-[10px] font-mono uppercase tracking-wider text-slate-400">{ranking.metric}</p>
                  </div>
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={ranking.trend_data} margin={{ top: 10, right: 16, bottom: 0, left: -12 }}>
                      <CartesianGrid stroke="#E2E8F0" strokeDasharray="3 3" vertical={false} />
                      <XAxis
                        dataKey="year"
                        tick={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, fill: "#64748B" }}
                        axisLine={{ stroke: "#0F172A" }}
                        tickLine={false}
                      />
                      <YAxis
                        tick={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, fill: "#64748B" }}
                        axisLine={false}
                        tickLine={false}
                        domain={["dataMin", "auto"]}
                      />
                      <Tooltip
                        contentStyle={{
                          background: "#0F172A",
                          border: "none",
                          fontFamily: "JetBrains Mono, monospace",
                          fontSize: 12,
                          color: "#fff",
                        }}
                        labelStyle={{ color: "#FCA5A5", marginBottom: 4 }}
                        formatter={(value) => [value, ranking.metric]}
                      />
                      <Line
                        type="monotone"
                        dataKey="value"
                        stroke="#DC2626"
                        strokeWidth={2.5}
                        dot={{ r: 4, fill: "#DC2626", stroke: "#fff", strokeWidth: 1.5 }}
                        activeDot={{ r: 6 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </motion.div>
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 gap-10 lg:grid-cols-12">
            <div className="lg:col-span-8" data-testid="ranking-description">
              <h2 className="border-b-2 border-slate-900 pb-4 font-serif text-2xl font-bold text-slate-900 sm:text-3xl">
                Mengapa Angka Ini Penting
              </h2>
              <div className="mt-6">
                {(ranking.description || "").split(/\n\s*\n/).map((p, i) => (
                  <p key={i} className={`mb-5 leading-relaxed ${i === 0 ? "text-lg font-medium text-slate-800" : "text-base text-slate-700"}`}>
                    {p}
                  </p>
                ))}
              </div>
            </div>
            <aside className="lg:col-span-4">
              <h3 className="font-mono text-xs font-bold uppercase tracking-[0.2em] text-slate-900">Indeks Lainnya</h3>
              <ul className="mt-5 divide-y divide-slate-300 border-t-2 border-slate-900">
                {others.map((r) => (
                  <li key={r.key}>
                    <Link
                      to={`/peringkat/${r.key}`}
                      data-testid={`related-ranking-${r.key}`}
                      className="group flex items-center justify-between py-4"
                    >
                      <div>
                        <p className="font-serif text-base font-semibold text-slate-900 transition-colors group-hover:text-red-700">{r.label}</p>
                        <p className="mt-0.5 text-xs font-mono text-slate-500">
                          {r.value} · #{r.rank}
                        </p>
                      </div>
                      <ArrowLeft size={16} className="rotate-180 text-slate-400 transition-transform group-hover:translate-x-1 group-hover:text-red-700" />
                    </Link>
                  </li>
                ))}
              </ul>
            </aside>
          </div>
        </section>
      </main>
      <Footer />
    </div>
  );
}
