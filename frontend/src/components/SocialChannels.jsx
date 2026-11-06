import { useState } from "react";
import { motion } from "framer-motion";
import { ExternalLink, Instagram, Youtube, Facebook, Twitter, Music2, Play, FileText, MessageSquare, BarChart2, Film, PenLine } from "lucide-react";

const PLATFORMS = ["Semua", "Instagram", "YouTube", "Facebook", "TikTok", "X"];

const PLATFORM_ICON = {
  Instagram: Instagram,
  YouTube: Youtube,
  Facebook: Facebook,
  TikTok: Music2,
  X: Twitter,
};

const PLATFORM_STYLE = {
  Instagram: "text-pink-600 border-pink-300",
  YouTube: "text-red-600 border-red-300",
  Facebook: "text-blue-600 border-blue-300",
  TikTok: "text-slate-900 border-slate-400",
  X: "text-slate-700 border-slate-400",
};

const TYPE_ICON = {
  Video: Play,
  Reels: Film,
  Post: FileText,
  Utas: MessageSquare,
  Infografis: BarChart2,
  Dokumenter: Film,
  Catatan: PenLine,
};

function TypeBadge({ type }) {
  const Icon = TYPE_ICON[type] || Play;
  return (
    <span className="inline-flex items-center gap-1 border border-slate-300 bg-white px-1.5 py-0.5 text-[9px] font-mono font-bold uppercase tracking-wider text-slate-600">
      <Icon size={10} /> {type}
    </span>
  );
}

export default function SocialChannels({ channels }) {
  const [platform, setPlatform] = useState("Semua");
  const filtered = channels.filter((c) => platform === "Semua" || c.platform === platform);

  return (
    <section id="konten-sosial" data-testid="social-channels" className="border-t-2 border-slate-900 bg-[#F1EFEA] py-14">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="mb-8 max-w-2xl">
          <p className="text-xs font-mono font-semibold uppercase tracking-[0.2em] text-red-700">Pengawal Digital</p>
          <h2 className="mt-2 font-serif text-2xl font-bold text-slate-900 sm:text-3xl lg:text-4xl">Konten yang Memberitakan Kabar Buruk</h2>
          <p className="mt-3 text-sm leading-relaxed text-slate-600">
            Kurasi kreator, kanal, dan akun media sosial yang gigih memberitakan skandal dan kebijakan bermasalah di Indonesia — lengkap dengan preview konten unggulannya.
          </p>
        </div>

        <div className="mb-8 flex flex-wrap gap-2" data-testid="platform-filters">
          {PLATFORMS.map((p) => (
            <button
              key={p}
              onClick={() => setPlatform(p)}
              data-testid={`platform-filter-${p.toLowerCase()}`}
              className={`border px-4 py-1.5 text-xs font-bold uppercase tracking-wider transition-colors ${
                platform === p
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-300 bg-white text-slate-600 hover:border-slate-900 hover:text-slate-900"
              }`}
            >
              {p}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {filtered.map((c, i) => {
            const Icon = PLATFORM_ICON[c.platform] || ExternalLink;
            const content = c.content || [];
            const featured = content[0];
            const rest = content.slice(1, 3);
            return (
              <motion.article
                key={c.id}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ duration: 0.45, delay: (i % 2) * 0.08 }}
                className="flex flex-col border border-slate-300 bg-white transition-shadow hover:shadow-[6px_6px_0_0_#0F172A]"
                data-testid={`channel-card-${c.id}`}
              >
                {/* header kanal */}
                <div className="flex items-start justify-between gap-3 p-5 pb-4">
                  <div className="flex items-center gap-3">
                    <span className={`grid h-11 w-11 shrink-0 place-items-center border ${PLATFORM_STYLE[c.platform] || "text-slate-600 border-slate-300"}`}>
                      <Icon size={20} />
                    </span>
                    <div>
                      <h3 className="font-serif text-lg font-bold leading-tight text-slate-900">{c.name}</h3>
                      <p className="text-xs font-mono text-slate-500">
                        {c.handle} · {c.followers} pengikut
                      </p>
                    </div>
                  </div>
                  <span className="shrink-0 font-mono text-[10px] font-bold uppercase tracking-wider text-slate-400">{c.platform}</span>
                </div>

                {/* preview konten utama */}
                {featured && (
                  <a
                    href={featured.url || c.url || "#"}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group/preview relative mx-5 block overflow-hidden border border-slate-200"
                    data-testid={`channel-preview-${c.id}`}
                  >
                    {featured.image_url && (
                      <img
                        src={featured.image_url}
                        alt={featured.title}
                        loading="lazy"
                        className="aspect-[16/8] w-full object-cover transition-transform duration-500 group-hover/preview:scale-105"
                      />
                    )}
                    <div className="absolute inset-0 flex flex-col justify-end bg-gradient-to-t from-slate-950/85 via-slate-950/30 to-transparent p-4">
                      <span className="mb-2 w-fit"><TypeBadge type={featured.type} /></span>
                      <p className="font-serif text-base font-bold leading-snug text-white">{featured.title}</p>
                      <p className="mt-1 text-[10px] font-mono uppercase tracking-wider text-slate-300">
                        {featured.date} · {featured.stats}
                      </p>
                    </div>
                    <span className="absolute right-3 top-3 grid h-9 w-9 place-items-center border border-white/40 bg-slate-950/50 text-white backdrop-blur-sm transition-colors group-hover/preview:bg-red-700">
                      <Play size={14} fill="currentColor" />
                    </span>
                  </a>
                )}

                {/* daftar konten */}
                <div className="flex-1 p-5 pt-4">
                  <p className="mb-3 text-[10px] font-mono font-bold uppercase tracking-[0.18em] text-slate-400">
                    Konten pilihan ({content.length})
                  </p>
                  <ul className="divide-y divide-slate-200 border-t border-slate-200">
                    {rest.map((item, j) => (
                      <li key={j}>
                        <a
                          href={item.url || c.url || "#"}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="group/item flex items-center gap-3 py-3"
                          data-testid={`channel-content-${c.id}-${j + 1}`}
                        >
                          {item.image_url && (
                            <img src={item.image_url} alt="" loading="lazy" className="h-12 w-20 shrink-0 border border-slate-200 object-cover" />
                          )}
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <TypeBadge type={item.type} />
                            </div>
                            <p className="mt-1 truncate text-sm font-semibold text-slate-800 transition-colors group-hover/item:text-red-700">
                              {item.title}
                            </p>
                            <p className="text-[10px] font-mono uppercase tracking-wider text-slate-400">
                              {item.date} · {item.stats}
                            </p>
                          </div>
                          <ExternalLink size={14} className="shrink-0 text-slate-300 transition-colors group-hover/item:text-red-700" />
                        </a>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-4 text-xs leading-relaxed text-slate-500">{c.focus}</p>
                  <a
                    href={c.url || "#"}
                    target="_blank"
                    rel="noopener noreferrer"
                    data-testid={`channel-visit-${c.id}`}
                    className="mt-4 inline-flex items-center gap-1.5 border-t border-slate-200 pt-3 text-[11px] font-mono font-bold uppercase tracking-wider text-slate-500 transition-colors hover:text-red-700"
                  >
                    Kunjungi kanal <ExternalLink size={12} />
                  </a>
                </div>
              </motion.article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
