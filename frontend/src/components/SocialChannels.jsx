import { useState } from "react";
import { motion } from "framer-motion";
import { ExternalLink, Instagram, Youtube, Facebook, Twitter, Music2 } from "lucide-react";

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
            Kurasi kreator, kanal, dan akun media sosial yang gigih memberitakan skandal dan kebijakan bermasalah di Indonesia — dari video esai panjang hingga utas pedas.
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

        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((c, i) => {
            const Icon = PLATFORM_ICON[c.platform] || ExternalLink;
            return (
              <motion.a
                key={c.id}
                href={c.url || "#"}
                target="_blank"
                rel="noopener noreferrer"
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ duration: 0.45, delay: (i % 3) * 0.08 }}
                className="group flex flex-col border border-slate-300 bg-white p-5 transition-shadow hover:shadow-[6px_6px_0_0_#0F172A]"
                data-testid={`channel-card-${c.id}`}
              >
                <div className="flex items-start justify-between">
                  <span className={`grid h-11 w-11 place-items-center border ${PLATFORM_STYLE[c.platform] || "text-slate-600 border-slate-300"}`}>
                    <Icon size={20} />
                  </span>
                  <span className="font-mono text-[10px] font-bold uppercase tracking-wider text-slate-400">{c.platform}</span>
                </div>
                <h3 className="mt-4 font-serif text-lg font-bold leading-snug text-slate-900 transition-colors group-hover:text-red-700">
                  {c.name}
                </h3>
                <p className="mt-0.5 text-xs font-mono text-slate-500">
                  {c.handle} · {c.followers} pengikut
                </p>
                <p className="mt-3 flex-1 text-sm leading-relaxed text-slate-600">{c.focus}</p>
                <p className="mt-4 flex items-center gap-1.5 border-t border-slate-200 pt-3 text-[11px] font-mono font-bold uppercase tracking-wider text-slate-500 transition-colors group-hover:text-red-700">
                  Kunjungi kanal <ExternalLink size={12} />
                </p>
              </motion.a>
            );
          })}
        </div>
      </div>
    </section>
  );
}
