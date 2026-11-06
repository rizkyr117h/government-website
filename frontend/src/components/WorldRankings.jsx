import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

const TREND_ICON = {
  naik: <TrendingUp size={13} className="text-emerald-700" />,
  turun: <TrendingDown size={13} className="text-red-700" />,
  stagnan: <Minus size={13} className="text-slate-500" />,
};

function AlertBadge() {
  return (
    <span
      data-testid="ranking-alert-badge"
      className="relative ml-1 inline-flex items-center gap-1.5 border border-red-500 bg-red-600/10 px-2 py-0.5 text-[9px] font-mono font-bold uppercase tracking-[0.15em] text-red-400"
    >
      <span className="relative flex h-2 w-2">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-red-600" />
      </span>
      Memburuk
    </span>
  );
}

export default function WorldRankings({ rankings }) {
  const worsened = rankings.filter((r) => r.trend === "turun").length;
  return (
    <section id="peringkat" data-testid="world-rankings" className="border-y-2 border-slate-900 bg-slate-900 py-14 text-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mb-10 max-w-2xl">
          <p className="flex flex-wrap items-center gap-3 text-xs font-mono font-semibold uppercase tracking-[0.2em] text-red-400">
            Indonesia vs Dunia
            {worsened > 0 && (
              <span className="inline-flex items-center gap-1.5 border border-red-500 px-2 py-0.5 text-[10px] tracking-[0.15em] text-red-400" data-testid="worsened-summary-badge">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-red-600" />
                </span>
                {worsened} indeks memburuk
              </span>
            )}
          </p>
          <h2 className="mt-2 font-serif text-2xl font-bold sm:text-3xl lg:text-4xl">Rapor Merah di Panggung Dunia</h2>
          <p className="mt-3 text-sm leading-relaxed text-slate-300">
            Posisi Indonesia dalam berbagai indeks global — dari korupsi, kebebasan pers, hingga pendidikan dan kesehatan. Klik tiap kartu untuk melihat tren tahunan dan sumber datanya.
          </p>
        </div>
        <div className="grid grid-cols-1 gap-px border border-slate-700 bg-slate-700 sm:grid-cols-2 lg:grid-cols-4">
          {rankings.map((r, i) => (
            <Link key={r.key} to={`/peringkat/${r.key}`} className="block" data-testid={`ranking-link-${r.key}`}>
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ duration: 0.45, delay: (i % 4) * 0.07 }}
                className="group flex h-full flex-col bg-slate-900 p-5 transition-colors hover:bg-slate-800"
                data-testid={`ranking-card-${r.key}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[10px] font-mono font-bold uppercase tracking-[0.18em] text-slate-400">
                    {r.label}
                    {r.trend === "turun" && <AlertBadge />}
                  </p>
                  {TREND_ICON[r.trend]}
                </div>
                <p className="mt-3 font-serif text-3xl font-black text-white">{r.value}</p>
                <p className="mt-1 text-xs font-mono text-red-400">
                  Peringkat {r.rank} <span className="text-slate-500">/ {r.total} negara</span>
                </p>
                <div className="mt-4 h-1.5 w-full bg-slate-700">
                  <div className={`h-full ${r.trend === "turun" ? "animate-pulse bg-red-500" : "bg-red-600"}`} style={{ width: `${r.pct}%` }} />
                </div>
                <p className="mt-4 flex-1 text-xs leading-relaxed text-slate-400">{r.note}</p>
                <p className="mt-3 border-t border-slate-800 pt-2 text-[10px] font-mono uppercase tracking-wider text-slate-500 transition-colors group-hover:text-red-400">
                  Lihat tren tahunan →
                </p>
              </motion.div>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}
