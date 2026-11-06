import { useMemo, useState } from "react";
import { motion } from "framer-motion";

const STATUSES = ["Semua", "Menggantung", "Dalam Proses Hukum", "Dihentikan/SP3", "Pengalihan Isu"];

const STATUS_STYLE = {
  "Menggantung": "border-amber-500 text-amber-700",
  "Dalam Proses Hukum": "border-red-600 text-red-700",
  "Dihentikan/SP3": "border-slate-400 text-slate-500",
  "Pengalihan Isu": "border-orange-500 text-orange-700",
};

export default function ScandalTracker({ scandals }) {
  const [status, setStatus] = useState("Semua");

  const filtered = useMemo(
    () => scandals.filter((s) => status === "Semua" || s.status === status),
    [scandals, status]
  );

  return (
    <section id="arsip" data-testid="scandal-tracker" className="mx-auto max-w-7xl px-4 py-14 sm:px-6 lg:px-8">
      <div className="mb-8 max-w-2xl">
        <p className="text-xs font-mono font-semibold uppercase tracking-[0.2em] text-red-700">Basis Data Kasus</p>
        <h2 className="mt-2 font-serif text-2xl font-bold text-slate-900 sm:text-3xl lg:text-4xl">Arsip Skandal</h2>
        <p className="mt-3 text-sm leading-relaxed text-slate-600">
          Rekam jejak kasus-kasus besar: siapa aktornya, berapa kerugiannya, dan di mana ujung proses hukumnya — kalau ada.
        </p>
      </div>

      <div className="mb-8 flex flex-wrap gap-2" data-testid="status-filters">
        {STATUSES.map((s) => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            data-testid={`status-filter-${s.toLowerCase().replace(/[\s/]+/g, "-")}`}
            className={`border px-4 py-1.5 text-xs font-bold uppercase tracking-wider transition-colors ${
              status === s
                ? "border-slate-900 bg-slate-900 text-white"
                : "border-slate-300 bg-white text-slate-600 hover:border-slate-900 hover:text-slate-900"
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      <div className="overflow-x-auto border border-slate-300 bg-white">
        <table className="w-full min-w-[720px] text-left text-sm" data-testid="scandal-table">
          <thead>
            <tr className="border-b-2 border-slate-900 text-[10px] font-mono font-bold uppercase tracking-[0.18em] text-slate-500">
              <th className="px-4 py-3">#</th>
              <th className="px-4 py-3">Kasus</th>
              <th className="px-4 py-3">Aktor Kunci</th>
              <th className="px-4 py-3">Periode</th>
              <th className="px-4 py-3">Kerugian</th>
              <th className="px-4 py-3">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {filtered.map((s, i) => (
              <motion.tr
                key={s.id}
                initial={{ opacity: 0 }}
                whileInView={{ opacity: 1 }}
                viewport={{ once: true }}
                transition={{ duration: 0.35, delay: i * 0.05 }}
                className="transition-colors hover:bg-red-50/50"
                data-testid={`scandal-row-${s.id}`}
              >
                <td className="px-4 py-4 font-mono text-xs text-slate-400">{String(i + 1).padStart(2, "0")}</td>
                <td className="px-4 py-4">
                  <p className="font-serif text-base font-bold text-slate-900">{s.title}</p>
                  <p className="mt-1 text-xs leading-relaxed text-slate-500">{s.summary}</p>
                </td>
                <td className="px-4 py-4 text-xs font-medium text-slate-700">{s.actor}</td>
                <td className="px-4 py-4 font-mono text-xs text-slate-500">{s.year}</td>
                <td className="px-4 py-4 font-mono text-xs font-bold text-red-700">{s.loss}</td>
                <td className="px-4 py-4">
                  <span className={`inline-block border px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider ${STATUS_STYLE[s.status]}`}>
                    {s.status}
                  </span>
                </td>
              </motion.tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
