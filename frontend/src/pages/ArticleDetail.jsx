import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { ArrowLeft, Flame, Frown, Eye, ThumbsUp, Clock, Send } from "lucide-react";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import { api, formatDate, formatApiErrorDetail } from "@/lib/api";

const REACTIONS = [
  { key: "marah", label: "Marah", icon: Flame },
  { key: "kecewa", label: "Kecewa", icon: Frown },
  { key: "waspada", label: "Waspada", icon: Eye },
];

export default function ArticleDetail() {
  const { slug } = useParams();
  const [article, setArticle] = useState(null);
  const [comments, setComments] = useState([]);
  const [notFound, setNotFound] = useState(false);
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/articles/${slug}`);
        setArticle(data);
        const c = await api.get(`/articles/${data.id}/comments`);
        setComments(c.data);
      } catch {
        setNotFound(true);
      }
    })();
  }, [slug]);

  const react = async (type) => {
    try {
      const { data } = await api.post(`/articles/${article.id}/react`, { type });
      setArticle((a) => ({ ...a, reactions: data }));
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const upvote = async (id) => {
    try {
      const { data } = await api.post(`/comments/${id}/upvote`);
      setComments((cs) => cs.map((c) => (c.id === id ? { ...c, upvotes: data.upvotes } : c)));
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail));
    }
  };

  const submitComment = async (e) => {
    e.preventDefault();
    if (!text.trim()) {
      toast.error("Tulis komentar dulu.");
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post(`/articles/${article.id}/comments`, { name, text });
      setComments((cs) => [data, ...cs]);
      setName("");
      setText("");
      toast.success("Komentar terkirim.");
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    } finally {
      setSubmitting(false);
    }
  };

  if (notFound) {
    return (
      <div className="min-h-screen bg-[#FAF8F5]">
        <Header />
        <div className="grid min-h-[50vh] place-items-center font-mono text-sm uppercase tracking-widest text-slate-500" data-testid="article-not-found">
          Artikel tidak ditemukan.
        </div>
        <Footer />
      </div>
    );
  }

  if (!article) {
    return (
      <div className="min-h-screen bg-[#FAF8F5]">
        <Header />
        <div className="grid min-h-[50vh] place-items-center font-mono text-sm uppercase tracking-widest text-slate-500">
          Memuat artikel…
        </div>
        <Footer />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#FAF8F5]" data-testid="article-detail-page">
      <Header />
      <article className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <Link
          to="/"
          data-testid="back-to-home"
          className="inline-flex items-center gap-2 text-xs font-mono font-semibold uppercase tracking-wider text-slate-500 transition-colors hover:text-red-700"
        >
          <ArrowLeft size={14} /> Kembali ke Beranda
        </Link>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.55 }}>
          <p className="mt-8 text-xs font-mono font-semibold uppercase tracking-[0.2em] text-red-700">
            {article.category} · {article.severity}
          </p>
          <h1 className="mt-3 font-serif text-3xl font-extrabold leading-tight tracking-tight text-slate-900 sm:text-4xl lg:text-5xl" data-testid="article-title">
            {article.title}
          </h1>
          <p className="mt-4 text-base leading-relaxed text-slate-600 sm:text-lg">{article.dek}</p>
          <div className="mt-6 flex flex-wrap items-center gap-4 border-y border-slate-300 py-3 text-xs font-mono text-slate-500">
            <span className="font-bold text-slate-700">{article.author}</span>
            <span>{formatDate(article.published_at)}</span>
            <span className="flex items-center gap-1.5">
              <Clock size={12} /> {article.reading_time} mnt baca
            </span>
            {article.loss_estimate && <span className="font-bold text-red-700">Kerugian: {article.loss_estimate}</span>}
          </div>
        </motion.div>
        <motion.img
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.7, delay: 0.2 }}
          src={article.image_url}
          alt={article.title}
          className="mt-8 aspect-[16/9] w-full border border-slate-300 object-cover"
          data-testid="article-image"
        />
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.3 }}
          className="prose-slate mt-8"
          data-testid="article-body"
        >
          {article.body.split(/\n\s*\n/).map((p, i) => (
            <p key={i} className={`mb-5 leading-relaxed text-slate-700 ${i === 0 ? "text-lg font-medium text-slate-800" : "text-base"}`}>
              {p}
            </p>
          ))}
        </motion.div>

        <div className="mt-10 border-y-2 border-slate-900 py-6" data-testid="reactions-bar">
          <p className="mb-4 text-xs font-mono font-bold uppercase tracking-[0.2em] text-slate-500">Reaksi Pembaca</p>
          <div className="flex flex-wrap gap-3">
            {REACTIONS.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => react(key)}
                data-testid={`react-${key}`}
                className="flex items-center gap-2 border border-slate-300 bg-white px-5 py-2.5 text-sm font-semibold text-slate-700 transition-colors hover:border-red-700 hover:text-red-700"
              >
                <Icon size={16} />
                {label}
                <span className="font-mono text-xs text-slate-400">{article.reactions?.[key] ?? 0}</span>
              </button>
            ))}
          </div>
        </div>

        <section className="mt-10" data-testid="comments-section">
          <h2 className="font-serif text-2xl font-bold text-slate-900">
            Komentar Pembaca <span className="font-mono text-sm font-normal text-slate-500">({comments.length})</span>
          </h2>
          <form onSubmit={submitComment} className="mt-6 border border-slate-300 bg-white p-5" data-testid="comment-form">
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Nama (boleh anonim)"
              data-testid="comment-name-input"
              className="mb-3 w-full border border-slate-300 bg-[#FAF8F5] px-3 py-2.5 text-sm outline-none transition-colors placeholder:text-slate-400 focus:border-red-700"
            />
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Sampaikan pendapatmu…"
              rows={4}
              data-testid="comment-text-input"
              className="w-full border border-slate-300 bg-[#FAF8F5] px-3 py-2.5 text-sm outline-none transition-colors placeholder:text-slate-400 focus:border-red-700"
            />
            <button
              type="submit"
              disabled={submitting}
              data-testid="comment-submit-button"
              className="mt-3 inline-flex items-center gap-2 border-2 border-slate-900 bg-slate-900 px-5 py-2.5 text-xs font-bold uppercase tracking-wider text-white transition-colors hover:bg-red-700 hover:border-red-700 disabled:opacity-50"
            >
              <Send size={14} /> {submitting ? "Mengirim…" : "Kirim Komentar"}
            </button>
          </form>
          <ul className="mt-8 space-y-4">
            {comments.length === 0 && (
              <p className="border border-dashed border-slate-300 bg-white p-6 text-center font-mono text-xs uppercase tracking-wider text-slate-500" data-testid="comments-empty">
                Belum ada komentar. Jadilah yang pertama bersuara.
              </p>
            )}
            {comments.map((c) => (
              <li key={c.id} className="border border-slate-300 bg-white p-4" data-testid={`comment-item-${c.id}`}>
                <div className="flex items-center justify-between">
                  <p className="text-sm font-bold text-slate-900">{c.name}</p>
                  <p className="font-mono text-[10px] uppercase tracking-wider text-slate-400">{formatDate(c.created_at)}</p>
                </div>
                <p className="mt-2 text-sm leading-relaxed text-slate-700">{c.text}</p>
                <button
                  onClick={() => upvote(c.id)}
                  data-testid={`comment-upvote-${c.id}`}
                  className="mt-3 inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 transition-colors hover:text-red-700"
                >
                  <ThumbsUp size={13} /> {c.upvotes} setuju
                </button>
              </li>
            ))}
          </ul>
        </section>
      </article>
      <Footer />
    </div>
  );
}
