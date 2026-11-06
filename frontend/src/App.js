import { useEffect } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import Lenis from "lenis";
import { AuthProvider } from "@/context/AuthContext";
import Home from "@/pages/Home";
import ArticleDetail from "@/pages/ArticleDetail";
import LoginPage from "@/pages/LoginPage";
import AdminPanel from "@/pages/AdminPanel";

function SmoothScroll() {
  useEffect(() => {
    const lenis = new Lenis({ duration: 1.05 });
    let raf;
    const loop = (time) => {
      lenis.raf(time);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
      lenis.destroy();
    };
  }, []);
  return null;
}

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <SmoothScroll />
          <ScrollToTop />
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/artikel/:slug" element={<ArticleDetail />} />
            <Route path="/masuk" element={<LoginPage />} />
            <Route path="/admin" element={<AdminPanel />} />
          </Routes>
          <Toaster position="bottom-right" richColors />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}

export default App;
