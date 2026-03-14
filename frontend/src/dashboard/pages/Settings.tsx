import { useEffect, useState } from "react";
import { api, getRole, getUsername, type AccountSummary, type AlertConfig } from "../api/client";

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

function SectionHeading({ children }: { children: React.ReactNode }) {
  return <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">{children}</h2>;
}

function ActionButton({
  onClick,
  disabled,
  variant = "default",
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  variant?: "default" | "danger";
  children: React.ReactNode;
}) {
  const base = "px-3 py-1 rounded text-xs font-medium transition-colors disabled:opacity-40";
  const styles =
    variant === "danger"
      ? `${base} bg-[#3a1a1a] text-red-400 hover:bg-[#5a2020] border border-red-900`
      : `${base} bg-[#2a2f45] text-slate-300 hover:bg-[#363d58] border border-[#404868]`;
  return (
    <button className={styles} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Password reset modal
// ---------------------------------------------------------------------------

function PasswordModal({
  username,
  onClose,
}: {
  username: string;
  onClose: () => void;
}) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    if (!password) { setError("Password is required"); return; }
    if (password !== confirm) { setError("Passwords do not match"); return; }
    setSaving(true);
    setError("");
    try {
      await api.resetAccountPassword(username, password);
      onClose();
    } catch {
      setError("Failed to reset password");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-[#1e2130] border-2 border-[#404868] rounded-lg p-6 w-full max-w-sm">
        <h3 className="text-sm font-semibold text-slate-200 mb-4">Reset password — {username}</h3>
        {error && <p className="text-red-400 text-xs mb-3">{error}</p>}
        <div className="space-y-3 mb-4">
          <input
            type="password"
            placeholder="New password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full bg-[#0f1117] border border-[#404868] rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-slate-400"
          />
          <input
            type="password"
            placeholder="Confirm password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className="w-full bg-[#0f1117] border border-[#404868] rounded px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-slate-400"
          />
        </div>
        <div className="flex gap-2 justify-end">
          <ActionButton onClick={onClose}>Cancel</ActionButton>
          <ActionButton onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </ActionButton>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Accounts section
// ---------------------------------------------------------------------------

function AccountsSection() {
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState("normal");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");
  const [passwordModal, setPasswordModal] = useState<string | null>(null);
  const currentUser = getUsername();

  useEffect(() => {
    api.getAccounts()
      .then(setAccounts)
      .catch(() => setError("Failed to load accounts"))
      .finally(() => setLoading(false));
  }, []);

  async function handleCreate() {
    if (!newUsername.trim() || !newPassword) {
      setCreateError("Username and password are required");
      return;
    }
    setCreating(true);
    setCreateError("");
    try {
      const account = await api.createAccount(newUsername.trim(), newPassword, newRole);
      setAccounts((prev) => [...prev, account]);
      setNewUsername("");
      setNewPassword("");
      setNewRole("normal");
    } catch (e: unknown) {
      setCreateError(e instanceof Error && e.message === "409" ? "Username already exists" : "Failed to create account");
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(username: string) {
    if (!confirm(`Delete account "${username}"?`)) return;
    try {
      await api.deleteAccount(username);
      setAccounts((prev) => prev.filter((a) => a.username !== username));
    } catch {
      alert("Failed to delete account");
    }
  }

  async function handleRoleChange(username: string, role: string) {
    try {
      await api.updateAccountRole(username, role);
      setAccounts((prev) => prev.map((a) => a.username === username ? { ...a, role } : a));
    } catch {
      alert("Failed to update role");
    }
  }

  if (loading) return <p className="text-sm text-slate-500">Loading accounts…</p>;
  if (error) return <p className="text-sm text-red-400">{error}</p>;

  return (
    <div>
      <SectionHeading>Accounts</SectionHeading>
      <table className="w-full text-sm mb-6">
        <thead>
          <tr className="text-left text-xs text-slate-500 border-b border-[#404868]">
            <th className="pb-2 font-medium">Username</th>
            <th className="pb-2 font-medium">Role</th>
            <th className="pb-2 font-medium text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {accounts.map((a) => {
            const isDefault = a.is_default === true;
            const isSelf = a.username === currentUser;
            return (
              <tr key={a.username} className="border-b border-[#2a2f45]">
                <td className="py-2 text-slate-200">
                  {a.username}
                  {isDefault && <span className="ml-2 text-xs text-slate-500">(built-in)</span>}
                  {isSelf && <span className="ml-2 text-xs text-slate-500">(you)</span>}
                </td>
                <td className="py-2">
                  {isDefault ? (
                    <span className="text-xs text-slate-400">admin</span>
                  ) : (
                    <select
                      value={a.role}
                      onChange={(e) => handleRoleChange(a.username, e.target.value)}
                      className="bg-[#0f1117] border border-[#404868] rounded px-2 py-0.5 text-xs text-slate-300 focus:outline-none"
                    >
                      <option value="admin">admin</option>
                      <option value="normal">normal</option>
                    </select>
                  )}
                </td>
                <td className="py-2 text-right">
                  <div className="flex gap-2 justify-end">
                    {!isDefault && (
                      <ActionButton onClick={() => setPasswordModal(a.username)}>
                        Reset password
                      </ActionButton>
                    )}
                    {!isDefault && (
                      <ActionButton variant="danger" onClick={() => handleDelete(a.username)}>
                        Delete
                      </ActionButton>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="bg-[#161a27] border border-[#404868] rounded-lg p-4">
        <p className="text-xs text-slate-400 font-medium mb-3">New account</p>
        {createError && <p className="text-red-400 text-xs mb-2">{createError}</p>}
        <div className="flex gap-2 flex-wrap">
          <input
            type="text"
            placeholder="Username"
            value={newUsername}
            onChange={(e) => setNewUsername(e.target.value)}
            className="bg-[#0f1117] border border-[#404868] rounded px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-slate-400 w-40"
          />
          <input
            type="password"
            placeholder="Password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="bg-[#0f1117] border border-[#404868] rounded px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-slate-400 w-40"
          />
          <select
            value={newRole}
            onChange={(e) => setNewRole(e.target.value)}
            className="bg-[#0f1117] border border-[#404868] rounded px-3 py-1.5 text-sm text-slate-300 focus:outline-none"
          >
            <option value="normal">normal</option>
            <option value="admin">admin</option>
          </select>
          <ActionButton onClick={handleCreate} disabled={creating}>
            {creating ? "Creating…" : "Create"}
          </ActionButton>
        </div>
      </div>

      {passwordModal && (
        <PasswordModal username={passwordModal} onClose={() => setPasswordModal(null)} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Alert config editor
// ---------------------------------------------------------------------------

type DetectorRow = {
  kind: string;
  threshold: string;
  period: string;
};

type SymbolOverride = {
  ticker: string;
  rows: DetectorRow[];
};

function parseAlertConfig(config: AlertConfig): { defaults: DetectorRow[]; overrides: SymbolOverride[] } {
  const defaults: DetectorRow[] = [];
  const overrides: SymbolOverride[] = [];

  const defaultSection = config["default"] as Record<string, unknown> | undefined;
  if (defaultSection) {
    for (const [kind, args] of Object.entries(defaultSection)) {
      const a = args as Record<string, unknown>;
      defaults.push({
        kind,
        threshold: String(a?.threshold ?? ""),
        period: String(a?.period ?? ""),
      });
    }
  }

  for (const [key, value] of Object.entries(config)) {
    if (key === "default" || key === "templates") continue;
    if (typeof value !== "object" || value === null) continue;
    const rows: DetectorRow[] = [];
    for (const [kind, args] of Object.entries(value as Record<string, unknown>)) {
      const a = args as Record<string, unknown>;
      rows.push({ kind, threshold: String(a?.threshold ?? ""), period: String(a?.period ?? "") });
    }
    overrides.push({ ticker: key, rows });
  }

  return { defaults, overrides };
}

function buildAlertConfig(defaults: DetectorRow[], overrides: SymbolOverride[]): AlertConfig {
  const config: AlertConfig = {};

  if (defaults.length > 0) {
    const defaultSection: Record<string, unknown> = {};
    for (const row of defaults) {
      if (!row.kind) continue;
      const args: Record<string, unknown> = { threshold: parseFloat(row.threshold) || 0 };
      if (row.period) args.period = row.period;
      defaultSection[row.kind] = args;
    }
    config["default"] = defaultSection;
  }

  for (const override of overrides) {
    if (!override.ticker) continue;
    const section: Record<string, unknown> = {};
    for (const row of override.rows) {
      if (!row.kind) continue;
      const args: Record<string, unknown> = { threshold: parseFloat(row.threshold) || 0 };
      if (row.period) args.period = row.period;
      section[row.kind] = args;
    }
    config[override.ticker] = section;
  }

  return config;
}

function AlertConfigEditor({
  username,
  label,
}: {
  username: string;
  label: string;
}) {
  const [defaults, setDefaults] = useState<DetectorRow[]>([]);
  const [overrides, setOverrides] = useState<SymbolOverride[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<"idle" | "saved" | "error">("idle");

  useEffect(() => {
    const fetcher = username === "__me__" ? api.getMyAlerts() : api.getAccountAlerts(username);
    fetcher
      .then((config) => {
        const parsed = parseAlertConfig(config);
        setDefaults(parsed.defaults);
        setOverrides(parsed.overrides);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [username]);

  async function handleSave() {
    setSaving(true);
    setStatus("idle");
    try {
      const config = buildAlertConfig(defaults, overrides);
      if (username === "__me__") {
        await api.updateMyAlerts(config);
      } else {
        await api.updateAccountAlerts(username, config);
      }
      setStatus("saved");
    } catch {
      setStatus("error");
    } finally {
      setSaving(false);
    }
  }

  function updateDefaultRow(i: number, field: keyof DetectorRow, value: string) {
    setDefaults((prev) => prev.map((r, idx) => idx === i ? { ...r, [field]: value } : r));
  }

  function addDefaultRow() {
    setDefaults((prev) => [...prev, { kind: "", threshold: "", period: "" }]);
  }

  function removeDefaultRow(i: number) {
    setDefaults((prev) => prev.filter((_, idx) => idx !== i));
  }

  function addOverride() {
    setOverrides((prev) => [...prev, { ticker: "", rows: [{ kind: "", threshold: "", period: "" }] }]);
  }

  function removeOverride(i: number) {
    setOverrides((prev) => prev.filter((_, idx) => idx !== i));
  }

  function updateOverrideTicker(i: number, ticker: string) {
    setOverrides((prev) => prev.map((o, idx) => idx === i ? { ...o, ticker } : o));
  }

  function updateOverrideRow(oi: number, ri: number, field: keyof DetectorRow, value: string) {
    setOverrides((prev) => prev.map((o, idx) =>
      idx === oi ? { ...o, rows: o.rows.map((r, ridx) => ridx === ri ? { ...r, [field]: value } : r) } : o
    ));
  }

  function addOverrideRow(oi: number) {
    setOverrides((prev) => prev.map((o, idx) =>
      idx === oi ? { ...o, rows: [...o.rows, { kind: "", threshold: "", period: "" }] } : o
    ));
  }

  function removeOverrideRow(oi: number, ri: number) {
    setOverrides((prev) => prev.map((o, idx) =>
      idx === oi ? { ...o, rows: o.rows.filter((_, ridx) => ridx !== ri) } : o
    ));
  }

  if (loading) return <p className="text-sm text-slate-500">Loading…</p>;

  const rowClass = "flex gap-2 items-center mb-1";
  const inputClass = "bg-[#0f1117] border border-[#404868] rounded px-2 py-1 text-xs text-slate-200 focus:outline-none focus:border-slate-400";

  return (
    <div>
      <p className="text-xs text-slate-400 font-medium mb-3">{label}</p>

      <p className="text-xs text-slate-500 mb-1">Default thresholds</p>
      {defaults.map((row, i) => (
        <div key={i} className={rowClass}>
          <input className={`${inputClass} w-36`} placeholder="kind (e.g. percent_change)" value={row.kind} onChange={(e) => updateDefaultRow(i, "kind", e.target.value)} />
          <input className={`${inputClass} w-24`} placeholder="threshold" value={row.threshold} onChange={(e) => updateDefaultRow(i, "threshold", e.target.value)} />
          <input className={`${inputClass} w-20`} placeholder="period" value={row.period} onChange={(e) => updateDefaultRow(i, "period", e.target.value)} />
          <button onClick={() => removeDefaultRow(i)} className="text-red-500 hover:text-red-400 text-xs px-1">✕</button>
        </div>
      ))}
      <ActionButton onClick={addDefaultRow}>+ detector</ActionButton>

      <p className="text-xs text-slate-500 mt-4 mb-1">Symbol overrides</p>
      {overrides.map((o, oi) => (
        <div key={oi} className="mb-3 pl-3 border-l border-[#404868]">
          <div className="flex gap-2 items-center mb-1">
            <input className={`${inputClass} w-24`} placeholder="ticker" value={o.ticker} onChange={(e) => updateOverrideTicker(oi, e.target.value.toUpperCase())} />
            <button onClick={() => removeOverride(oi)} className="text-red-500 hover:text-red-400 text-xs px-1">✕ remove</button>
          </div>
          {o.rows.map((row, ri) => (
            <div key={ri} className={rowClass}>
              <input className={`${inputClass} w-36`} placeholder="kind" value={row.kind} onChange={(e) => updateOverrideRow(oi, ri, "kind", e.target.value)} />
              <input className={`${inputClass} w-24`} placeholder="threshold" value={row.threshold} onChange={(e) => updateOverrideRow(oi, ri, "threshold", e.target.value)} />
              <input className={`${inputClass} w-20`} placeholder="period" value={row.period} onChange={(e) => updateOverrideRow(oi, ri, "period", e.target.value)} />
              <button onClick={() => removeOverrideRow(oi, ri)} className="text-red-500 hover:text-red-400 text-xs px-1">✕</button>
            </div>
          ))}
          <ActionButton onClick={() => addOverrideRow(oi)}>+ detector</ActionButton>
        </div>
      ))}
      <ActionButton onClick={addOverride}>+ symbol override</ActionButton>

      <div className="mt-4 flex gap-3 items-center">
        <ActionButton onClick={handleSave} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </ActionButton>
        {status === "saved" && <span className="text-xs text-green-400">Saved</span>}
        {status === "error" && <span className="text-xs text-red-400">Save failed</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Alert configs section (admin view — one tab per account)
// ---------------------------------------------------------------------------

function AlertConfigsSection({ accounts }: { accounts: AccountSummary[] }) {
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const currentUser = getUsername();

  const tabs = accounts.map((a) => ({
    username: a.is_default ? a.username : a.username,
    label: a.is_default ? `${a.username} (default admin)` : a.username,
    apiKey: a.username,
  }));

  const selected = activeTab ?? (tabs[0]?.username ?? null);

  return (
    <div>
      <SectionHeading>Alert Configurations</SectionHeading>
      <div className="flex gap-1 mb-4 flex-wrap">
        {tabs.map((t) => (
          <button
            key={t.username}
            onClick={() => setActiveTab(t.username)}
            className={[
              "px-3 py-1 rounded text-xs border transition-colors",
              selected === t.username
                ? "bg-[#1e2130] border-[#404868] text-slate-200"
                : "bg-[#0f1117] border-[#2a2f45] text-slate-500 hover:text-slate-300",
            ].join(" ")}
          >
            {t.label}
            {t.username === currentUser && " (you)"}
          </button>
        ))}
      </div>
      {selected && (
        <AlertConfigEditor
          key={selected}
          username={selected}
          label={`Alert thresholds for ${selected}`}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inner tab bar
// ---------------------------------------------------------------------------

function InnerTab({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={[
        "px-4 py-1.5 text-xs font-medium border-b-2 transition-colors",
        active
          ? "border-slate-400 text-slate-200"
          : "border-transparent text-slate-500 hover:text-slate-300",
      ].join(" ")}
    >
      {label}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Main Settings page
// ---------------------------------------------------------------------------

export default function Settings() {
  const isAdmin = getRole() === "admin";
  const [activeTab, setActiveTab] = useState<"users" | "alerts">(isAdmin ? "users" : "alerts");
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
  const [accountsLoaded, setAccountsLoaded] = useState(false);

  useEffect(() => {
    if (!isAdmin) return;
    api.getAccounts()
      .then((list) => { setAccounts(list); setAccountsLoaded(true); })
      .catch(() => setAccountsLoaded(true));
  }, [isAdmin]);

  return (
    <div>
      <div className="flex gap-1 border-b border-[#404868] mb-6">
        {isAdmin && (
          <InnerTab label="Users" active={activeTab === "users"} onClick={() => setActiveTab("users")} />
        )}
        <InnerTab label="Alert Configurations" active={activeTab === "alerts"} onClick={() => setActiveTab("alerts")} />
      </div>

      {activeTab === "users" && isAdmin && <AccountsSection />}

      {activeTab === "alerts" && (
        isAdmin
          ? accountsLoaded && <AlertConfigsSection accounts={accounts} />
          : <AlertConfigEditor username="__me__" label="My alert thresholds" />
      )}
    </div>
  );
}
