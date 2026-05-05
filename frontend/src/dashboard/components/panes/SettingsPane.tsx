import { useEffect, useState } from "react";
import { api, getRole, getUsername, type AccountSummary } from "../../api/client";
import { DropdownSelector } from "../inputs";

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
  variant?: "default" | "danger" | "remove";
  children: React.ReactNode;
}) {
  const base = "px-3 py-1 rounded text-xs font-medium transition-colors disabled:opacity-40 cursor-pointer";
  const styles =
    variant === "danger"
      ? `${base} bg-[#3a1a1a] text-red-400 hover:bg-[#5a2020] border border-red-900`
      : variant === "remove"
      ? "text-red-500 hover:text-red-400 text-xs px-1 cursor-pointer transition-colors"
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
// General section
// ---------------------------------------------------------------------------

function GeneralSection({ isDefaultAdmin }: { isDefaultAdmin: boolean }) {
  const [showPasswordModal, setShowPasswordModal] = useState(false);
  const username = getUsername();

  return (
    <div>
      <SectionHeading>General</SectionHeading>
      <div className="bg-[#161a27] border border-[#404868] rounded-lg p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-slate-300">Password</p>
            {isDefaultAdmin && (
              <p className="text-xs text-slate-500 mt-0.5">Managed by application config</p>
            )}
          </div>
          <ActionButton onClick={() => setShowPasswordModal(true)} disabled={isDefaultAdmin}>
            Change password
          </ActionButton>
        </div>
      </div>
      {showPasswordModal && username && (
        <PasswordModal username={username} onClose={() => setShowPasswordModal(false)} />
      )}
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
                    <DropdownSelector
                      value={a.role}
                      onChange={(v) => handleRoleChange(a.username, v)}
                      options={[{ value: "admin", label: "admin" }, { value: "normal", label: "normal" }]}
                      className="w-28"
                    />
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
          <DropdownSelector
            value={newRole}
            onChange={setNewRole}
            options={[{ value: "normal", label: "normal" }, { value: "admin", label: "admin" }]}
            className="w-32"
          />
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
// Alert configs section
// ---------------------------------------------------------------------------

function AlertConfigsSection() {
  return (
    <div>
      <SectionHeading>Alert Configurations</SectionHeading>
      <p className="text-sm text-slate-500">
        Alert rules are managed via the CLI (<code className="text-slate-400">nexus alert --help</code>).
        A UI for managing channels and rules is coming soon.
      </p>
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

export default function SettingsPane() {
  const isAdmin = getRole() === "admin";
  const currentUser = getUsername();
  const [activeTab, setActiveTab] = useState<"general" | "users" | "alerts">("general");
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
  const [accountsLoaded, setAccountsLoaded] = useState(false);

  useEffect(() => {
    if (!isAdmin) return;
    api.getAccounts()
      .then((list) => { setAccounts(list); setAccountsLoaded(true); })
      .catch(() => setAccountsLoaded(true));
  }, [isAdmin]);

  const isDefaultAdmin = isAdmin && accountsLoaded
    ? accounts.find((a) => a.username === currentUser)?.is_default === true
    : false;

  return (
    <div>
      <div className="flex gap-1 border-b border-[#404868] mb-6">
        <InnerTab label="General" active={activeTab === "general"} onClick={() => setActiveTab("general")} />
        {isAdmin && (
          <InnerTab label="Users" active={activeTab === "users"} onClick={() => setActiveTab("users")} />
        )}
        <InnerTab label="Alert Configurations" active={activeTab === "alerts"} onClick={() => setActiveTab("alerts")} />
      </div>

      {activeTab === "general" && <GeneralSection isDefaultAdmin={isDefaultAdmin} />}
      {activeTab === "users" && isAdmin && <AccountsSection />}
      {activeTab === "alerts" && <AlertConfigsSection />}
    </div>
  );
}
