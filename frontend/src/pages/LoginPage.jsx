import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ShieldCheck, LogIn } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { LogoMark } from "@/components/Header";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    const err = await login(email, password);
    setLoading(false);
    if (err) {
      setError(err);
    } else {
      navigate("/admin");
    }
  };

  return (
    <div className="grid min-h-screen place-items-center bg-[#FAF8F5] px-4" data-testid="login-page">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-sm border-2 border-slate-900 bg-white p-8 shadow-[8px_8px_0_0_#0F172A]"
      >
        <div className="mb-6 flex items-center gap-3">
          <LogoMark className="w-10 h-10" />
          <div>
            <p className="font-serif text-xl font-black text-slate-900">Portal Redaksi</p>
            <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-500">Akses terbatas</p>
          </div>
        </div>
        <form onSubmit={submit}>
          <label className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-600">Email</label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            data-testid="admin-email-input"
            className="mb-4 w-full border border-slate-300 bg-[#FAF8F5] px-3 py-2.5 text-sm outline-none focus:border-red-700"
            placeholder="admin@kaburburuk.id"
          />
          <label className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-600">Kata Sandi</label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            data-testid="admin-password-input"
            className="mb-4 w-full border border-slate-300 bg-[#FAF8F5] px-3 py-2.5 text-sm outline-none focus:border-red-700"
            placeholder="••••••••"
          />
          {error && (
            <p className="mb-4 border border-red-300 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700" data-testid="login-error">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            data-testid="admin-login-button"
            className="flex w-full items-center justify-center gap-2 border-2 border-slate-900 bg-slate-900 py-3 text-xs font-bold uppercase tracking-wider text-white transition-colors hover:bg-red-700 hover:border-red-700 disabled:opacity-50"
          >
            {loading ? <ShieldCheck size={15} className="animate-pulse" /> : <LogIn size={15} />}
            {loading ? "Memeriksa…" : "Masuk Redaksi"}
          </button>
        </form>
        <Link to="/" data-testid="login-back-home" className="mt-5 block text-center text-xs font-mono uppercase tracking-wider text-slate-500 hover:text-red-700">
          ← Kembali ke situs
        </Link>
      </motion.div>
    </div>
  );
}
