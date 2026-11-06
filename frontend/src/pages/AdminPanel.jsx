import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { toast } from "sonner";
import { LogOut, Plus, Pencil, Trash2, Save, X, Newspaper, MessageSquare, BarChart3 } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { LogoMark } from "@/components/Header";
import { api, formatDate, formatApiErrorDetail } from "@/lib/api";

const CATEGORIES = ["Korupsi", "Skandal", "Kontroversi", "Kebijakan", "Pemilu"];
const SEVERITIES = ["Kritis", "Tinggi", "Sedang"];

const EMPTY_ARTICLE = {
  title: "",
  category: "Korupsi",
  severity: "Sedang",
  dek: "",
  body: "",
  image_url: "",
  author: "Redaksi Kabar Buruk",
  loss_estimate: "",
  reading_time: 5,
};

const inputCls =
  "w-full border border-slate-300 bg-[#FAF8F5] px-3 py-2 text-sm outline-none transition-colors focus:border-red-700";

export default function AdminPanel() {
  const { user, logout } = useAuth();
  const [tab, setTab] = useState("artikel");
  const [articles, setArticles] = useState([]);
  const [comments, setComments] = useState([]);
  const [rankings, setRankings] = useState([]);
  const [editing, setEditing] = useState(null);

  useEffect(() => {
    if (!user) return;
    api.get("/articles").then((r) => setArticles(r.data));
    api.get("/admin/comments").then((r) => setComments(r.data));
    api.get("/rankings").then((r) => setRankings(r.data));
  }, [user]);

  if (user === null) {
    return (
      <div className="grid min-h-screen place-items-center bg-[#FAF8F5] font-mono text-sm uppercase tracking-widest text-slate-500">
        Memeriksa sesi…
      </div>
    );
  }
  if (user === false) return <Navigate to="/masuk" replace />;

  const saveArticle = async (e) => {
    e.preventDefault();
    try {
      if (editing.id) {
        const { data } = await api.put(`/articles/${editing.id}`, editing);
        setArticles((as) => as.map((a) => (a.id === data.id ? data : a)));
        toast.success("Artikel diperbarui.");
      } else {
        const { data } = await api.post("/articles", editing);
        setArticles((as) => [data, ...as]);
        toast.success("Artikel diterbitkan.");
      }
      setEditing(null);
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  const deleteArticle = async (id) => {
    if (!window.confirm("Hapus artikel ini beserta komentarnya?")) return;
    await api.delete(`/articles/${id}`);
    setArticles((as) => as.filter((a) => a.id !== id));
    toast.success("Artikel dihapus.");
  };

  const deleteComment = async (id) => {
    await api.delete(`/admin/comments/${id}`);
    setComments((cs) => cs.filter((c) => c.id !== id));
    toast.success("Komentar dihapus.");
  };

  const saveRanking = async (r) => {
    try {
      const { data } = await api.put(`/admin/rankings/${r.key}`, {
        value: r.value,
        rank: Number(r.rank),
        note: r.note,
      });
      setRankings((rs) => rs.map((x) => (x.key === data.key ? data : x)));
      toast.success(`"${r.label}" diperbarui.`);
    } catch (err) {
      toast.error(formatApiErrorDetail(err.response?.data?.detail));
    }
  };

  const TABS = [
    ["artikel", "Artikel", Newspaper],
    ["komentar", "Komentar", MessageSquare],
    ["peringkat", "Peringkat", BarChart3],
  ];

  return (
    <div className="min-h-screen bg-[#FAF8F5]" data-testid="admin-panel">
      <header className="border-b-2 border-slate-900 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4 sm:px-6">
          <div className="flex items-center gap-3">
            <LogoMark className="w-9 h-9" />
            <div>
              <p className="font-serif text-lg font-black text-slate-900">Dasbor Redaksi</p>
              <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-slate-500">{user.email}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Link to="/" data-testid="admin-view-site" className="border border-slate-300 px-3 py-2 text-xs font-bold uppercase tracking-wider text-slate-600 transition-colors hover:border-slate-900 hover:text-slate-900">
              Lihat Situs
            </Link>
            <button
              onClick={logout}
              data-testid="admin-logout-button"
              className="flex items-center gap-1.5 border border-red-700 px-3 py-2 text-xs font-bold uppercase tracking-wider text-red-700 transition-colors hover:bg-red-700 hover:text-white"
            >
              <LogOut size={13} /> Keluar
            </button>
          </div>
        </div>
        <div className="mx-auto flex max-w-6xl gap-1 px-4 sm:px-6">
          {TABS.map(([key, label, Icon]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              data-testid={`admin-tab-${key}`}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-bold uppercase tracking-wider transition-colors ${
                tab === key ? "border-red-700 text-red-700" : "border-transparent text-slate-500 hover:text-slate-900"
              }`}
            >
              <Icon size={14} /> {label}
            </button>
          ))}
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
        {tab === "artikel" && (
          <div>
            {editing ? (
              <form onSubmit={saveArticle} className="border-2 border-slate-900 bg-white p-6" data-testid="article-form">
                <div className="mb-5 flex items-center justify-between">
                  <h2 className="font-serif text-xl font-bold text-slate-900">
                    {editing.id ? "Sunting Artikel" : "Tulis Artikel Baru"}
                  </h2>
                  <button type="button" onClick={() => setEditing(null)} data-testid="article-form-cancel" className="text-slate-400 hover:text-red-700">
                    <X size={20} />
                  </button>
                </div>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <div className="sm:col-span-2">
                    <label className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-600">Judul</label>
                    <input required value={editing.title} onChange={(e) => setEditing({ ...editing, title: e.target.value })} data-testid="article-title-input" className={inputCls} />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-600">Kategori</label>
                    <select value={editing.category} onChange={(e) => setEditing({ ...editing, category: e.target.value })} data-testid="article-category-select" className={inputCls}>
                      {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-600">Tingkat Keparahan</label>
                    <select value={editing.severity} onChange={(e) => setEditing({ ...editing, severity: e.target.value })} data-testid="article-severity-select" className={inputCls}>
                      {SEVERITIES.map((s) => <option key={s}>{s}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-600">Penulis</label>
                    <input value={editing.author} onChange={(e) => setEditing({ ...editing, author: e.target.value })} data-testid="article-author-input" className={inputCls} />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-600">Estimasi Kerugian (opsional)</label>
                    <input value={editing.loss_estimate || ""} onChange={(e) => setEditing({ ...editing, loss_estimate: e.target.value })} data-testid="article-loss-input" className={inputCls} placeholder="Rp 8 T" />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-600">URL Gambar</label>
                    <input value={editing.image_url} onChange={(e) => setEditing({ ...editing, image_url: e.target.value })} data-testid="article-image-input" className={inputCls} placeholder="https://…" />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-600">Dek / Ringkasan</label>
                    <textarea rows={2} value={editing.dek} onChange={(e) => setEditing({ ...editing, dek: e.target.value })} data-testid="article-dek-input" className={inputCls} />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-600">Isi Artikel (pisahkan paragraf dengan baris kosong)</label>
                    <textarea rows={9} required value={editing.body} onChange={(e) => setEditing({ ...editing, body: e.target.value })} data-testid="article-body-input" className={inputCls} />
                  </div>
                </div>
                <button
                  type="submit"
                  data-testid="article-save-button"
                  className="mt-5 inline-flex items-center gap-2 border-2 border-slate-900 bg-slate-900 px-6 py-2.5 text-xs font-bold uppercase tracking-wider text-white transition-colors hover:bg-red-700 hover:border-red-700"
                >
                  <Save size={14} /> Simpan
                </button>
              </form>
            ) : (
              <div>
                <div className="mb-6 flex items-center justify-between">
                  <h2 className="font-serif text-2xl font-bold text-slate-900">Artikel ({articles.length})</h2>
                  <button
                    onClick={() => setEditing({ ...EMPTY_ARTICLE })}
                    data-testid="article-new-button"
                    className="flex items-center gap-2 border-2 border-slate-900 bg-slate-900 px-4 py-2 text-xs font-bold uppercase tracking-wider text-white transition-colors hover:bg-red-700 hover:border-red-700"
                  >
                    <Plus size={14} /> Artikel Baru
                  </button>
                </div>
                <div className="divide-y divide-slate-200 border border-slate-300 bg-white" data-testid="admin-article-list">
                  {articles.map((a) => (
                    <div key={a.id} className="flex items-center justify-between gap-4 px-4 py-3" data-testid={`admin-article-${a.id}`}>
                      <div className="min-w-0">
                        <p className="truncate font-serif text-sm font-bold text-slate-900">{a.title}</p>
                        <p className="text-[11px] font-mono uppercase tracking-wider text-slate-500">
                          {a.category} · {formatDate(a.published_at)} · {a.views} tayang
                        </p>
                      </div>
                      <div className="flex shrink-0 gap-2">
                        <button onClick={() => setEditing({ ...a, loss_estimate: a.loss_estimate || "" })} data-testid={`article-edit-${a.id}`} className="border border-slate-300 p-2 text-slate-600 transition-colors hover:border-slate-900 hover:text-slate-900" aria-label="Sunting">
                          <Pencil size={14} />
                        </button>
                        <button onClick={() => deleteArticle(a.id)} data-testid={`article-delete-${a.id}`} className="border border-slate-300 p-2 text-slate-600 transition-colors hover:border-red-700 hover:text-red-700" aria-label="Hapus">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {tab === "komentar" && (
          <div>
            <h2 className="mb-6 font-serif text-2xl font-bold text-slate-900">Moderasi Komentar ({comments.length})</h2>
            {comments.length === 0 ? (
              <p className="border border-dashed border-slate-300 bg-white p-10 text-center font-mono text-xs uppercase tracking-wider text-slate-500" data-testid="admin-comments-empty">
                Belum ada komentar pembaca.
              </p>
            ) : (
              <div className="divide-y divide-slate-200 border border-slate-300 bg-white" data-testid="admin-comment-list">
                {comments.map((c) => (
                  <div key={c.id} className="flex items-start justify-between gap-4 px-4 py-3" data-testid={`admin-comment-${c.id}`}>
                    <div className="min-w-0">
                      <p className="text-sm font-bold text-slate-900">{c.name}</p>
                      <p className="mt-0.5 text-sm text-slate-600">{c.text}</p>
                      <p className="mt-1 truncate text-[11px] font-mono uppercase tracking-wider text-slate-400">
                        di: {c.article_title} · {c.upvotes} setuju
                      </p>
                    </div>
                    <button onClick={() => deleteComment(c.id)} data-testid={`comment-delete-${c.id}`} className="shrink-0 border border-slate-300 p-2 text-slate-600 transition-colors hover:border-red-700 hover:text-red-700" aria-label="Hapus komentar">
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {tab === "peringkat" && (
          <div>
            <h2 className="mb-6 font-serif text-2xl font-bold text-slate-900">Data Peringkat Dunia</h2>
            <div className="space-y-4" data-testid="admin-ranking-list">
              {rankings.map((r, i) => (
                <div key={r.key} className="grid grid-cols-1 gap-3 border border-slate-300 bg-white p-4 sm:grid-cols-[1fr_120px_100px_2fr_auto] sm:items-end" data-testid={`admin-ranking-${r.key}`}>
                  <div>
                    <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-slate-500">{r.label}</label>
                    <input value={r.value} onChange={(e) => setRankings((rs) => rs.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} data-testid={`ranking-value-${r.key}`} className={inputCls} />
                  </div>
                  <div>
                    <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-slate-500">Peringkat</label>
                    <input type="number" value={r.rank} onChange={(e) => setRankings((rs) => rs.map((x, j) => (j === i ? { ...x, rank: e.target.value } : x)))} data-testid={`ranking-rank-${r.key}`} className={inputCls} />
                  </div>
                  <div className="text-xs font-mono text-slate-500 sm:pb-2.5">/ {r.total} negara</div>
                  <div>
                    <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-slate-500">Catatan</label>
                    <input value={r.note} onChange={(e) => setRankings((rs) => rs.map((x, j) => (j === i ? { ...x, note: e.target.value } : x)))} data-testid={`ranking-note-${r.key}`} className={inputCls} />
                  </div>
                  <button onClick={() => saveRanking(r)} data-testid={`ranking-save-${r.key}`} className="flex items-center justify-center gap-1.5 border-2 border-slate-900 bg-slate-900 px-4 py-2 text-xs font-bold uppercase tracking-wider text-white transition-colors hover:bg-red-700 hover:border-red-700">
                    <Save size={13} /> Simpan
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
