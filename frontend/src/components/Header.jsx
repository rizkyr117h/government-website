import { Link } from "react-router-dom";
import { Search, ShieldCheck } from "lucide-react";
import EditorialMarquee from "@/components/EditorialMarquee";

export const LogoMark = ({ className = "w-10 h-10" }) => (
  <svg viewBox="0 0 40 40" className={className} data-testid="logo-mark" aria-hidden="true">
    <rect width="40" height="40" rx="5" fill="#DC2626" />
    <rect x="4.5" y="4.5" width="31" height="31" rx="2.5" fill="none" stroke="#fff" strokeWidth="1.6" />
    <path d="M14 10.5v19 M14 19.5 L25 10.5 M16.4 17.2 L25.4 29.5" stroke="#fff" strokeWidth="3.6" strokeLinecap="square" fill="none" />
  </svg>
);

export default function Header() {
  const today = new Date().toLocaleDateString("id-ID", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  const scrollTo = (id) => (e) => {
    e.preventDefault();
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <header data-testid="site-header" className="sticky top-0 z-50 border-b border-slate-900 bg-[#FAF8F5]/90 backdrop-blur-md">
      <div className="flex items-center justify-between border-b border-slate-300 bg-slate-900 px-4 py-1 text-[11px] font-mono tracking-wider text-slate-300 sm:px-6 lg:px-8">
        <span data-testid="header-date">{today}</span>
        <span className="hidden sm:block">EDISI DARING — JAKARTA</span>
      </div>
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
        <Link to="/" data-testid="header-logo-link" className="flex items-center gap-3">
          <LogoMark />
          <div className="leading-none">
            <span className="block font-serif text-2xl font-black tracking-tight text-slate-900 sm:text-3xl">
              KABAR BURUK
            </span>
            <span className="mt-1 block text-[10px] font-mono font-semibold uppercase tracking-[0.22em] text-slate-500">
              Berita yang tak enak didengar penguasa
            </span>
          </div>
        </Link>
        <nav className="hidden items-center gap-6 text-sm font-semibold text-slate-700 md:flex">
          <a href="#beranda" onClick={scrollTo("beranda")} data-testid="nav-beranda" className="transition-colors hover:text-red-700">
            Beranda
          </a>
          <a href="#arsip" onClick={scrollTo("arsip")} data-testid="nav-arsip" className="transition-colors hover:text-red-700">
            Arsip Skandal
          </a>
          <a href="#peringkat" onClick={scrollTo("peringkat")} data-testid="nav-peringkat" className="transition-colors hover:text-red-700">
            Peringkat Dunia
          </a>
          <a href="#konten-sosial" onClick={scrollTo("konten-sosial")} data-testid="nav-konten-sosial" className="transition-colors hover:text-red-700">
            Konten Sosial
          </a>
        </nav>
        <div className="flex items-center gap-2">
          <a
            href={`${process.env.REACT_APP_BACKEND_URL}/api/edisi-mingguan`}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="header-edisi-link"
            className="hidden h-10 items-center gap-2 border border-red-700 bg-red-700 px-3 text-xs font-semibold uppercase tracking-wider text-white transition-colors hover:bg-red-800 sm:flex"
          >
            Edisi Mingguan
          </a>
          <a
            href="#pencarian"
            onClick={scrollTo("pencarian")}
            data-testid="header-search-button"
            aria-label="Cari berita"
            className="grid h-10 w-10 place-items-center border border-slate-300 bg-white text-slate-700 transition-colors hover:border-slate-900 hover:text-slate-900"
          >
            <Search size={17} />
          </a>
          <Link
            to="/admin"
            data-testid="header-admin-link"
            className="flex h-10 items-center gap-2 border border-slate-900 bg-slate-900 px-3 text-xs font-semibold uppercase tracking-wider text-white transition-colors hover:bg-red-700 hover:border-red-700"
          >
            <ShieldCheck size={15} />
            <span className="hidden sm:inline">Redaksi</span>
          </Link>
        </div>
      </div>
      <EditorialMarquee />
    </header>
  );
}
