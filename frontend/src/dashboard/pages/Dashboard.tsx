import { useNavigate } from "react-router-dom";
import { clearToken } from "../api/client";

export default function Dashboard() {
  const navigate = useNavigate();

  function handleSignOut() {
    clearToken();
    navigate("/login");
  }

  return (
    <div className="min-h-screen bg-[#0f1117] text-slate-300">
      <nav className="bg-[#1e2130] border-b-2 border-[#404868] px-6 py-3 flex justify-between items-center">
        <span className="font-semibold tracking-wide text-slate-100">Portfolio Monitor</span>
        <button
          onClick={handleSignOut}
          className="text-sm text-slate-400 hover:text-slate-100 transition-colors"
        >
          Sign out
        </button>
      </nav>
      <div className="max-w-4xl mx-auto p-8">
        <h1 className="text-2xl font-semibold mb-4 text-slate-100">Dashboard</h1>
        <p className="text-slate-400">Portfolio monitoring dashboard — coming soon.</p>
      </div>
    </div>
  );
}
