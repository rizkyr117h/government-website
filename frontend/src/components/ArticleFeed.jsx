import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Search, Clock } from "lucide-react";
import { formatDate } from "@/lib/api";

const CATEGORIES = ["Semua", "Korupsi", "Skandal", "Kontroversi", "Kebijakan", "Pemilu"];

const SEVERITY_STYLE = {
  Kritis: "bg-red-700 text-white",
  Tinggi: "bg-amber-600 text-white",
  Sedang: "bg-slate-600 text-white",
};

export default function ArticleFeed({ articles }) {
  const [category, setCategory] = useState("Semua");
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return articles.filter((a) => {
      const matchCat = category === "Semua" || a.category === category;
      const matchQ =
        !q ||
        a.title.toLowerCase().includes(q) ||
        a.dek.toLowerCase().includes(q) ||
        a.body.toLowerCase().includes(q);
      return matchCat && matchQ;
    });
  }, [articles, category, query]);

  return (
    <section id="pencarian" data-testid="article-feed" className="mx-auto max-w-7xl px-4 py-14 sm:px-6 lg:px-8">
      <div className="mb-8 flex flex-col gap-6 border-b-2 border-slate-900 pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-mono font-semibold uppercase tracking-[0.2em] text-red-700">Arsip Berita</p>
          <h2 className="mt-2 font-serif text-2xl font-bold text-slate-900 sm:text-3xl lg:text-4xl">Liputan Terbaru</h2>
        </div>
        <div className="relative w-full lg:w-80">
          <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Cari skandal, nama, kasus…"
            data-testid="article-search-input"
            className="w-full border border-slate-300 bg-white py-2.5 pl-9 pr-3 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-red-700"
          />
        </div>
      </div>

      <div className="mb-10 flex flex-wrap gap-2" data-testid="category-filters">
        {CATEGORIES.map((c) => (
          <button
            key={c}
            onClick={() => setCategory(c)}
            data-testid={`filter-${c.toLowerCase()}`}
            className={`border px-4 py-1.5 text-xs font-bold uppercase tracking-wider transition-colors ${
              category === c
                ? "border-slate-900 bg-slate-900 text-white"
                : "border-slate-300 bg-white text-slate-600 hover:border-slate-900 hover:text-slate-900"
            }`}
          >
            {c}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <p className="border border-dashed border-slate-300 bg-white p-10 text-center font-mono text-sm text-slate-500" data-testid="feed-empty">
          Tidak ada berita yang cocok. Coba kata kunci lain.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-x-8 gap-y-12 md:grid-cols-2 lg:grid-cols-3">
          {filtered.map((a, i) => (
            <motion.article
              key={a.id}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.5, delay: (i % 3) * 0.08 }}
              className="group flex flex-col border border-slate-300 bg-white transition-shadow hover:shadow-[6px_6px_0_0_#0F172A]"
              data-testid={`article-card-${a.id}`}
            >
              <Link to={`/artikel/${a.slug}`} className="block overflow-hidden">
                <img
                  src={a.image_url}
                  alt={a.title}
                  loading="lazy"
                  className="aspect-[16/10] w-full object-cover transition-transform duration-500 group-hover:scale-105"
                />
              </Link>
              <div className="flex flex-1 flex-col p-5">
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 text-[10px] font-mono font-bold uppercase tracking-wider ${SEVERITY_STYLE[a.severity] || SEVERITY_STYLE.Sedang}`}>
                    {a.severity}
                  </span>
                  <span className="text-[10px] font-mono font-semibold uppercase tracking-wider text-slate-500">{a.category}</span>
                </div>
                <Link to={`/artikel/${a.slug}`} className="mt-3">
                  <h3 className="font-serif text-xl font-bold leading-snug text-slate-900 transition-colors group-hover:text-red-700">
                    {a.title}
                  </h3>
                </Link>
                <p className="mt-2 line-clamp-3 text-sm leading-relaxed text-slate-600">{a.dek}</p>
                <div className="mt-auto flex items-center justify-between pt-5 text-[11px] font-mono text-slate-500">
                  <span className="flex items-center gap-1.5">
                    <Clock size={12} />
                    {a.reading_time} mnt · {formatDate(a.published_at)}
                  </span>
                  {a.loss_estimate && <span className="font-bold text-red-700">{a.loss_estimate}</span>}
                </div>
              </div>
            </motion.article>
          ))}
        </div>
      )}
    </section>
  );
}
