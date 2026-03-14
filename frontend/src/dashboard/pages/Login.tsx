import { useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, setToken } from "../api/client";

export default function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await api.login(username, password);
      if (result.token) {
        setToken(result.token);
        if (result.username) localStorage.setItem("auth_username", result.username);
        if (result.role) localStorage.setItem("auth_role", result.role);
        navigate("/");
      } else {
        setError(result.error ?? "Invalid credentials");
      }
    } catch {
      setError("Could not connect to server");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#0f1117] flex items-center justify-center">
      <div className="bg-[#1e2130] border-2 border-[#404868] p-8 rounded-lg w-full max-w-sm">
        <h1 className="text-xl font-semibold mb-6 text-slate-100">Portfolio Monitor</h1>
        {error && (
          <p className="text-red-400 text-sm mb-4">{error}</p>
        )}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1 text-slate-300" htmlFor="username">
              Username
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
              className="w-full bg-[#0f1117] border-2 border-[#404868] rounded px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-slate-400"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1 text-slate-300" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full bg-[#0f1117] border-2 border-[#404868] rounded px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-slate-400"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-slate-600 hover:bg-slate-500 text-slate-100 py-2 rounded text-sm font-medium transition-colors disabled:opacity-50"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
