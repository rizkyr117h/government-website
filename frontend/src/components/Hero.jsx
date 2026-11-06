import { useRef } from "react";
import { Link } from "react-router-dom";
import { motion, useScroll, useTransform } from "framer-motion";
import { ArrowRight, TrendingDown } from "lucide-react";
import { formatDate } from "@/lib/api";

function MaskedLine({ children, delay = 0, className = "" }) {
  return (
    <span className={`block overflow-hidden ${className}`}>
      <motion.span
        className="block"
        initial={{ y: "110%" }}
        animate={{ y: 0 }}
        transition={{ duration: 0.85, delay, ease: [0.22, 1, 0.36, 1] }}
      >
        {children}
      </motion.span>
    </span>
  );
}

const STATUS_COLOR = {
  "Menggantung": "bg-amber-500",
  "Dalam Proses Hukum": "bg-red-600",
  "Dihentikan/SP3": "bg-slate-500",
  "Pengalihan Isu": "bg-orange-500",
};

export default function Hero({ article, scandals }) {
  const imgRef = useRef(null);
  const { scrollYProgress } = useScroll({ target: imgRef, offset: ["start end", "end start"] });
  const y = useTransform(scrollYProgress, [0, 1], ["-8%", "8%"]);

  if (!article) return null;

  const titleWords = article.title.split(" ");
  const lines = [
    titleWords.slice(0, 4).join(" "),
    titleWords.slice(4).join(" "),
  ];

  return (
    <section id="beranda" data-testid="hero-section" className="border-b border-slate-900">
      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-0 px-4 py-10 sm:px-6 lg:grid-cols-12 lg:gap-8 lg:py-16 lg:px-8">
        <div className="lg:col-span-8 lg:pr-8">
          <motion.p
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="mb-4 flex items-center gap-3 text-xs font-mono font-semibold uppercase tracking-[0.2em] text-red-700"
            data-testid="hero-category"
          >
            <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-red-600" />
            Laporan Utama — {article.category}
          </motion.p>
          <h1 className="font-serif text-4xl font-extrabold leading-[1.08] tracking-tight text-slate-900 sm:text-5xl lg:text-6xl" data-testid="hero-headline">
            {lines.map((line, i) => (
              <MaskedLine key={i} delay={0.15 + i * 0.15}>
                {line}
              </MaskedLine>
            ))}
          </h1>
          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.5 }}
            className="mt-6 max-w-2xl text-base leading-relaxed text-slate-600 sm:text-lg"
            data-testid="hero-dek"
          >
            {article.dek}
          </motion.p>
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.65 }}
            className="mt-6 flex flex-wrap items-center gap-4"
          >
            <Link
              to={`/artikel/${article.slug}`}
              data-testid="hero-read-button"
              className="group inline-flex items-center gap-2 border-2 border-slate-900 bg-slate-900 px-6 py-3 text-sm font-bold uppercase tracking-wider text-white transition-colors hover:bg-red-700 hover:border-red-700"
            >
              Baca Investigasi
              <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" />
            </Link>
            <span className="text-xs font-mono text-slate-500">
              {article.author} · {formatDate(article.published_at)} · {article.reading_time} mnt baca
            </span>
          </motion.div>
          <motion.div
            ref={imgRef}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.4 }}
            className="relative mt-10 overflow-hidden border border-slate-300"
          >
            <motion.img
              src={article.image_url}
              alt={article.title}
              style={{ y }}
              className="h-[280px] w-full scale-110 object-cover sm:h-[380px]"
              data-testid="hero-image"
            />
            <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-slate-950/80 to-transparent px-4 pb-3 pt-10 text-[11px] font-mono uppercase tracking-widest text-white/80">
              <span>Dokumentasi lapangan</span>
              {article.loss_estimate && <span className="text-red-300">Estimasi kerugian {article.loss_estimate}</span>}
            </div>
          </motion.div>
        </div>

        <aside className="mt-10 border-t border-slate-900 pt-8 lg:col-span-4 lg:mt-0 lg:border-l lg:border-t-0 lg:pl-8 lg:pt-0" data-testid="hero-sidebar">
          <h2 className="flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-[0.2em] text-slate-900">
            <TrendingDown size={14} className="text-red-700" />
            Kawat Skandal
          </h2>
          <ul className="mt-5 divide-y divide-slate-300">
            {scandals.slice(0, 4).map((s, i) => (
              <motion.li
                key={s.id}
                initial={{ opacity: 0, x: 16 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: i * 0.08 }}
                className="group py-4"
                data-testid={`scandal-wire-${i}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="font-serif text-base font-semibold leading-snug text-slate-900 transition-colors group-hover:text-red-700">
                    {s.title}
                  </p>
                  <span className={`mt-1.5 inline-block h-2.5 w-2.5 shrink-0 rounded-full ${STATUS_COLOR[s.status] || "bg-slate-400"}`} title={s.status} />
                </div>
                <p className="mt-1 text-xs font-mono text-slate-500">
                  {s.status} · {s.year}
                </p>
              </motion.li>
            ))}
          </ul>
          <div className="mt-6 grid grid-cols-3 divide-x divide-slate-900 border-y-2 border-slate-900 py-4 text-center">
            {[
              ["Rp 300T+", "Kerugian terdokumentasi"],
              ["#115", "Indeks korupsi"],
              ["#111", "Kebebasan pers"],
            ].map(([v, l], i) => (
              <div key={i} className="px-2" data-testid={`hero-stat-${i}`}>
                <p className="font-serif text-xl font-black text-red-700 sm:text-2xl">{v}</p>
                <p className="mt-1 text-[10px] font-mono uppercase tracking-wider text-slate-500">{l}</p>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </section>
  );
}
