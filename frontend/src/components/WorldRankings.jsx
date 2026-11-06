import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

const TREND_ICON = {
  naik: <TrendingUp size={13} className="text-emerald-700" />,
  turun: <TrendingDown size={13} className="text-red-700" />,
  stagnan: <Minus size={13} className="text-slate-500" />,
};

export default function WorldRankings({ rankings }) {
  return (
    <section id="peringkat" data-testid="world-rankings" className="border-y-2 border-slate-900 bg-slate-900 py-14 text-white">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mb-10 max-w-2xl">
          <p className="text-xs font-mono font-semibold uppercase tracking-[0.2em] text-red-400">Indonesia vs Dunia</p>
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
                <div className="flex items-center justify-between">
                  <p className="text-[10px] font-mono font-bold uppercase tracking-[0.18em] text-slate-400">{r.label}</p>
                  {TREND_ICON[r.trend]}
                </div>
                <p className="mt-3 font-serif text-3xl font-black text-white">{r.value}</p>
                <p className="mt-1 text-xs font-mono text-red-400">
                  Peringkat {r.rank} <span className="text-slate-500">/ {r.total} negara</span>
                </p>
                <div className="mt-4 h-1.5 w-full bg-slate-700">
                  <div className="h-full bg-red-600" style={{ width: `${r.pct}%` }} />
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
