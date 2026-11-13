import { Link } from "react-router-dom";
import { LogoMark } from "@/components/Header";

export default function Footer() {
  return (
    <footer data-testid="site-footer" className="border-t-2 border-slate-900 bg-[#FAF8F5]">
      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-10 px-4 py-12 sm:px-6 md:grid-cols-3 lg:px-8">
        <div>
          <div className="flex items-center gap-3">
            <LogoMark className="w-9 h-9" />
            <span className="font-serif text-xl font-black tracking-tight text-slate-900">KABAR BURUK</span>
          </div>
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-slate-600">
            Dokumentasi independen atas skandal, korupsi, dan kontroversi politik Indonesia. Kami menulis kabar yang tak enak didengar penguasa — karena publik berhak tahu.
          </p>
        </div>
        <div>
          <p className="text-xs font-mono font-bold uppercase tracking-[0.2em] text-slate-500">Rubrik</p>
          <ul className="mt-4 space-y-2 text-sm font-semibold text-slate-700">
            <li><a href="#pencarian" className="transition-colors hover:text-red-700" data-testid="footer-liputan">Liputan Terbaru</a></li>
            <li><a href="#arsip" className="transition-colors hover:text-red-700" data-testid="footer-arsip">Arsip Skandal</a></li>
            <li><a href="#peringkat" className="transition-colors hover:text-red-700" data-testid="footer-peringkat">Peringkat Dunia</a></li>
            <li><a href="#konten-sosial" className="transition-colors hover:text-red-700" data-testid="footer-konten-sosial">Konten Sosial</a></li>
            <li>
              <a
                href={`${process.env.REACT_APP_BACKEND_URL}/api/edisi-mingguan`}
                target="_blank"
                rel="noopener noreferrer"
                className="font-bold text-red-700 transition-colors hover:text-red-800"
                data-testid="footer-edisi-link"
              >
                Unduh Edisi Mingguan (PDF)
              </a>
            </li>
          </ul>
        </div>
        <div>
          <p className="text-xs font-mono font-bold uppercase tracking-[0.2em] text-slate-500">Redaksi</p>
          <p className="mt-4 text-sm leading-relaxed text-slate-600">
            Punya bocoran dokumen atau informasi publik? Kirim ke redaksi. Identitas pelapor dijamin kerahasiaannya.
          </p>
        </div>
      </div>
      <div className="border-t border-slate-300 py-4 text-center text-[11px] font-mono uppercase tracking-wider text-slate-500">
        © {new Date().getFullYear()} Kabar Buruk · Konten bersifat dokumentasi & kritik jurnalistik
      </div>
    </footer>
  );
}
