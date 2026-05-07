import { useEffect, useState } from "react";
import {
  api,
  getRole,
  getUsername,
  type AccountSummary,
  type AlertChannelConfig,
  type AlertChannelConfigFull,
  type AlertSubscription,
} from "../../api/client";
import { Button } from "../buttons";
import { DropdownSelector } from "../inputs";

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

function SectionHeading({ children }: { children: React.ReactNode }) {
  return <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">{children}</h2>;
}

function TextInput({
  value,
  onChange,
  placeholder,
  type = "text",
  className = "",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  className?: string;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={`bg-[#0f1117] border border-[#404868] rounded px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-slate-400 ${className}`}
    />
  );
}

function TypeBadge({ type }: { type: string }) {
  return (
    <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#2a2f45] text-slate-400 uppercase tracking-wide">
      {type}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Password reset modal
// ---------------------------------------------------------------------------

function PasswordModal({ username, onClose }: { username: string; onClose: () => void }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    if (!password) { setError("Password is required"); return; }
    if (password !== confirm) { setError("Passwords do not match"); return; }
    setSaving(true); setError("");
    try { await api.resetAccountPassword(username, password); onClose(); }
    catch { setError("Failed to reset password"); }
    finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-[#1e2130] border-2 border-[#404868] rounded-lg p-6 w-full max-w-sm">
        <h3 className="text-sm font-semibold text-slate-200 mb-4">Reset password — {username}</h3>
        {error && <p className="text-red-400 text-xs mb-3">{error}</p>}
        <div className="space-y-3 mb-4">
          <TextInput type="password" placeholder="New password" value={password} onChange={setPassword} className="w-full" />
          <TextInput type="password" placeholder="Confirm password" value={confirm} onChange={setConfirm} className="w-full" />
        </div>
        <div className="flex gap-2 justify-end">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={handleSave} disabled={saving}>{saving ? "Saving…" : "Save"}</Button>
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
            {isDefaultAdmin && <p className="text-xs text-slate-500 mt-0.5">Managed by application config</p>}
          </div>
          <Button variant="default" onClick={() => setShowPasswordModal(true)} disabled={isDefaultAdmin}>Change password</Button>
        </div>
      </div>
      {showPasswordModal && username && (
        <PasswordModal username={username} onClose={() => setShowPasswordModal(false)} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Accounts section (admin only)
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
    api.getAccounts().then(setAccounts).catch(() => setError("Failed to load accounts")).finally(() => setLoading(false));
  }, []);

  async function handleCreate() {
    if (!newUsername.trim() || !newPassword) { setCreateError("Username and password are required"); return; }
    setCreating(true); setCreateError("");
    try {
      const account = await api.createAccount(newUsername.trim(), newPassword, newRole);
      setAccounts((prev) => [...prev, account]);
      setNewUsername(""); setNewPassword(""); setNewRole("normal");
    } catch (e: unknown) {
      setCreateError(e instanceof Error && e.message === "409" ? "Username already exists" : "Failed to create account");
    } finally { setCreating(false); }
  }

  async function handleDelete(username: string) {
    if (!confirm(`Delete account "${username}"?`)) return;
    try { await api.deleteAccount(username); setAccounts((prev) => prev.filter((a) => a.username !== username)); }
    catch { alert("Failed to delete account"); }
  }

  async function handleRoleChange(username: string, role: string) {
    try {
      await api.updateAccountRole(username, role);
      setAccounts((prev) => prev.map((a) => a.username === username ? { ...a, role } : a));
    } catch { alert("Failed to update role"); }
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
                    {!isDefault && <Button variant="default" onClick={() => setPasswordModal(a.username)}>Reset password</Button>}
                    {!isDefault && <Button variant="danger" onClick={() => handleDelete(a.username)}>Delete</Button>}
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
          <TextInput placeholder="Username" value={newUsername} onChange={setNewUsername} className="w-40" />
          <TextInput type="password" placeholder="Password" value={newPassword} onChange={setNewPassword} className="w-40" />
          <DropdownSelector
            value={newRole}
            onChange={setNewRole}
            options={[{ value: "normal", label: "normal" }, { value: "admin", label: "admin" }]}
            className="w-32"
          />
          <Button variant="primary" onClick={handleCreate} disabled={creating}>{creating ? "Creating…" : "Create"}</Button>
        </div>
      </div>

      {passwordModal && <PasswordModal username={passwordModal} onClose={() => setPasswordModal(null)} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Channel config form (shared between add and edit)
// ---------------------------------------------------------------------------

const CHANNEL_TYPES = [{ value: "matrix", label: "Matrix" }];

function ChannelConfigForm({
  initial,
  onSave,
  onCancel,
  saving,
  error,
}: {
  initial: { name: string; type: string; config: Record<string, unknown> };
  onSave: (name: string, type: string, config: Record<string, unknown>) => void;
  onCancel: () => void;
  saving: boolean;
  error: string;
}) {
  const [name, setName] = useState(initial.name);
  const [type, setType] = useState(initial.type || "matrix");
  const [homeserver, setHomeserver] = useState(String(initial.config["homeserver"] ?? ""));
  const [accessToken, setAccessToken] = useState(String(initial.config["access_token"] ?? ""));
  const [showToken, setShowToken] = useState(false);

  function buildConfig(): Record<string, unknown> {
    if (type === "matrix") return { homeserver: homeserver.trim(), access_token: accessToken.trim() };
    return {};
  }

  return (
    <div className="bg-[#161a27] border border-[#404868] rounded-lg p-4 space-y-3">
      {error && <p className="text-red-400 text-xs">{error}</p>}
      <div className="flex gap-3 flex-wrap items-end">
        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-slate-500 uppercase tracking-wide">Name</label>
          <TextInput value={name} onChange={setName} placeholder="e.g. Bitforged Matrix" className="w-48" />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[10px] text-slate-500 uppercase tracking-wide">Type</label>
          <DropdownSelector value={type} onChange={setType} options={CHANNEL_TYPES} className="w-36" />
        </div>
      </div>

      {type === "matrix" && (
        <div className="flex gap-3 flex-wrap items-end">
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-slate-500 uppercase tracking-wide">Homeserver</label>
            <TextInput value={homeserver} onChange={setHomeserver} placeholder="https://matrix.example.com" className="w-64" />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-slate-500 uppercase tracking-wide">Access Token</label>
            <div className="flex gap-1">
              <TextInput
                type={showToken ? "text" : "password"}
                value={accessToken}
                onChange={setAccessToken}
                placeholder="syt_…"
                className="w-52 font-mono text-xs"
              />
              <button
                onClick={() => setShowToken((v) => !v)}
                className="px-2 text-xs text-slate-500 hover:text-slate-300 transition-colors"
                title={showToken ? "Hide" : "Show"}
              >
                {showToken ? "Hide" : "Show"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="flex gap-2 pt-1">
        <Button variant="primary" onClick={() => onSave(name, type, buildConfig())} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Admin: Alert Channels section
// ---------------------------------------------------------------------------

function AdminAlertChannelsSection() {
  const [configs, setConfigs] = useState<AlertChannelConfigFull[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  useEffect(() => {
    api.listAdminChannelConfigs()
      .then(setConfigs)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function handleCreate(name: string, type: string, config: Record<string, unknown>) {
    if (!name.trim()) { setFormError("Name is required"); return; }
    setSaving(true); setFormError("");
    try {
      const created = await api.createChannelConfig({ type, name: name.trim(), config });
      setConfigs((prev) => [...prev, created]);
      setAdding(false);
    } catch { setFormError("Failed to create channel"); }
    finally { setSaving(false); }
  }

  async function handleUpdate(id: string, name: string, type: string, config: Record<string, unknown>) {
    if (!name.trim()) { setFormError("Name is required"); return; }
    setSaving(true); setFormError("");
    try {
      await api.updateChannelConfig(id, { name: name.trim(), config });
      setConfigs((prev) => prev.map((c) => c.id === id ? { ...c, name: name.trim(), type, config } : c));
      setEditId(null);
    } catch { setFormError("Failed to update channel"); }
    finally { setSaving(false); }
  }

  async function handleDelete(id: string) {
    try {
      await api.deleteChannelConfig(id);
      setConfigs((prev) => prev.filter((c) => c.id !== id));
    } catch { alert("Failed to delete channel"); }
    finally { setConfirmDelete(null); }
  }

  if (loading) return <p className="text-sm text-slate-500">Loading…</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <SectionHeading>Alert Channels</SectionHeading>
        {!adding && <Button variant="ghost" onClick={() => { setAdding(true); setEditId(null); setFormError(""); }}>Add</Button>}
      </div>

      {configs.length === 0 && !adding && (
        <p className="text-sm text-slate-500">No alert channels configured.</p>
      )}

      <div className="space-y-2 mb-4">
        {configs.map((c) => (
          <div key={c.id}>
            {editId === c.id ? (
              <ChannelConfigForm
                initial={{ name: c.name, type: c.type, config: c.config }}
                onSave={(name, type, config) => handleUpdate(c.id, name, type, config)}
                onCancel={() => { setEditId(null); setFormError(""); }}
                saving={saving}
                error={formError}
              />
            ) : (
              <div className="flex items-center justify-between bg-[#161a27] border border-[#404868] rounded-lg px-4 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-slate-200">{c.name}</span>
                  <TypeBadge type={c.type} />
                </div>
                {confirmDelete === c.id ? (
                  <div className="flex items-center gap-2">
                    <Button variant="danger" onClick={() => handleDelete(c.id)}>Confirm delete</Button>
                    <Button variant="ghost" onClick={() => setConfirmDelete(null)}>Cancel</Button>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <Button variant="default" onClick={() => { setEditId(c.id); setAdding(false); setFormError(""); }}>Edit</Button>
                    <Button variant="danger" onClick={() => setConfirmDelete(c.id)}>Delete</Button>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {adding && (
        <ChannelConfigForm
          initial={{ name: "", type: "matrix", config: {} }}
          onSave={handleCreate}
          onCancel={() => { setAdding(false); setFormError(""); }}
          saving={saving}
          error={formError}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// User: Alert Configurations section
// ---------------------------------------------------------------------------

const MODE_OPTIONS = [
  { value: "default", label: "Default" },
  { value: "opt_in", label: "Opt-in" },
  { value: "off", label: "Off" },
];

function targetPlaceholder(type: string): string {
  if (type === "matrix") return "@you:matrix.server.com";
  return "Target";
}

function AlertConfigsSection() {
  const [available, setAvailable] = useState<AlertChannelConfig[]>([]);
  const [subs, setSubs] = useState<AlertSubscription[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  // add/edit form state
  const [formChannelId, setFormChannelId] = useState("");
  const [formTarget, setFormTarget] = useState("");
  const [formMode, setFormMode] = useState<string>("default");
  const [formSaving, setFormSaving] = useState(false);
  const [formError, setFormError] = useState("");

  useEffect(() => {
    Promise.all([api.getAvailableChannels(), api.getMyAlerts()])
      .then(([channels, config]) => {
        setAvailable(channels);
        setSubs(config.subscriptions);
        if (channels.length > 0) setFormChannelId(channels[0].id);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  function openAdd() {
    const firstId = available[0]?.id ?? "";
    setFormChannelId(firstId);
    setFormTarget("");
    setFormMode("default");
    setFormError("");
    setEditId(null);
    setAdding(true);
  }

  function openEdit(sub: AlertSubscription) {
    setFormChannelId(sub.channel_config_id);
    setFormTarget(sub.target);
    setFormMode(sub.mode);
    setFormError("");
    setAdding(false);
    setEditId(sub.id);
  }

  async function handleAdd() {
    if (!formChannelId) { setFormError("Select a channel"); return; }
    setFormSaving(true); setFormError("");
    try {
      const created = await api.addSubscription({ channel_config_id: formChannelId, target: formTarget, mode: formMode });
      setSubs((prev) => [...prev, created]);
      setFormTarget("");
      setFormMode("default");
    } catch { setFormError("Failed to add"); }
    finally { setFormSaving(false); }
  }

  async function handleUpdate() {
    if (!editId) return;
    setFormSaving(true); setFormError("");
    try {
      await api.updateSubscription(editId, { target: formTarget, mode: formMode });
      setSubs((prev) => prev.map((s) => s.id === editId ? { ...s, target: formTarget, mode: formMode as AlertSubscription["mode"] } : s));
      setEditId(null);
    } catch { setFormError("Failed to save"); }
    finally { setFormSaving(false); }
  }

  async function handleDelete(id: string) {
    try {
      await api.deleteSubscription(id);
      setSubs((prev) => prev.filter((s) => s.id !== id));
    } catch { alert("Failed to delete"); }
    finally { setConfirmDelete(null); }
  }

  const channelOptions = available.map((ch) => ({ value: ch.id, label: `${ch.name} (${ch.type})` }));

  if (loading) return <p className="text-sm text-slate-500">Loading…</p>;

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <SectionHeading>Alert Configurations</SectionHeading>
        {!adding && available.length > 0 && (
          <Button variant="ghost" onClick={openAdd}>Add</Button>
        )}
      </div>

      {subs.length === 0 && !adding && (
        <p className="text-sm text-slate-500">
          {available.length === 0
            ? "No alert channels have been configured by an administrator yet."
            : "No channel subscriptions yet. Click Add to set one up."}
        </p>
      )}

      <div className="space-y-2">
        {subs.map((sub) => {
          const ch = available.find((c) => c.id === sub.channel_config_id);
          return (
            <div key={sub.id}>
              {editId === sub.id ? (
                <div className="bg-[#161a27] border border-[#404868] rounded-lg px-4 py-3 space-y-3">
                  {formError && <p className="text-red-400 text-xs">{formError}</p>}
                  <div className="flex gap-3 flex-wrap items-end">
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] text-slate-500 uppercase tracking-wide">Channel</label>
                      <DropdownSelector value={formChannelId} onChange={setFormChannelId} options={channelOptions} className="w-52" />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-[10px] text-slate-500 uppercase tracking-wide">Delivery</label>
                      <DropdownSelector value={formMode} onChange={setFormMode} options={MODE_OPTIONS} className="w-28" />
                    </div>
                    <div className="flex flex-col gap-1 flex-1">
                      <label className="text-[10px] text-slate-500 uppercase tracking-wide">Target</label>
                      <TextInput value={formTarget} onChange={setFormTarget} placeholder={targetPlaceholder(ch?.type ?? "")} className="w-full min-w-[200px]" />
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="primary" onClick={handleUpdate} disabled={formSaving}>{formSaving ? "Saving…" : "Save"}</Button>
                    <Button variant="ghost" onClick={() => setEditId(null)}>Cancel</Button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-between bg-[#161a27] border border-[#404868] rounded-lg px-4 py-2.5">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-slate-200">{sub.channel_name}</span>
                      <TypeBadge type={sub.channel_type} />
                    </div>
                    <span className="text-xs text-slate-500">{sub.mode}</span>
                    {sub.target && <span className="text-xs text-slate-400 truncate">{sub.target}</span>}
                  </div>
                  {confirmDelete === sub.id ? (
                    <div className="flex items-center gap-2 shrink-0">
                      <Button variant="danger" onClick={() => handleDelete(sub.id)}>Confirm delete</Button>
                      <Button variant="ghost" onClick={() => setConfirmDelete(null)}>Cancel</Button>
                    </div>
                  ) : (
                    <div className="flex gap-2 shrink-0">
                      <Button variant="default" onClick={() => openEdit(sub)}>Edit</Button>
                      <Button variant="danger" onClick={() => setConfirmDelete(sub.id)}>Delete</Button>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {adding && (
          <div className="bg-[#161a27] border border-[#404868] rounded-lg px-4 py-3 space-y-3">
            {formError && <p className="text-red-400 text-xs">{formError}</p>}
            <div className="flex gap-3 flex-wrap items-end">
              <div className="flex flex-col gap-1">
                <label className="text-[10px] text-slate-500 uppercase tracking-wide">Channel</label>
                <DropdownSelector value={formChannelId} onChange={setFormChannelId} options={channelOptions} className="w-52" />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-[10px] text-slate-500 uppercase tracking-wide">Delivery</label>
                <DropdownSelector value={formMode} onChange={setFormMode} options={MODE_OPTIONS} className="w-28" />
              </div>
              <div className="flex flex-col gap-1 flex-1">
                <label className="text-[10px] text-slate-500 uppercase tracking-wide">Target</label>
                <TextInput
                  value={formTarget}
                  onChange={setFormTarget}
                  placeholder={targetPlaceholder(available.find((c) => c.id === formChannelId)?.type ?? "")}
                  className="w-full min-w-[200px]"
                />
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="primary" onClick={handleAdd} disabled={formSaving}>{formSaving ? "Adding…" : "Add"}</Button>
              <Button variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>
            </div>
          </div>
        )}
      </div>
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
        active ? "border-slate-400 text-slate-200" : "border-transparent text-slate-500 hover:text-slate-300",
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
  const [activeTab, setActiveTab] = useState<"general" | "users" | "channels" | "alerts">("general");
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
        <InnerTab label="Alert Configurations" active={activeTab === "alerts"} onClick={() => setActiveTab("alerts")} />
        <div className="flex-1" />
        {isAdmin && (
          <InnerTab label="Users" active={activeTab === "users"} onClick={() => setActiveTab("users")} />
        )}
        {isAdmin && (
          <InnerTab label="Channels" active={activeTab === "channels"} onClick={() => setActiveTab("channels")} />
        )}
      </div>

      {activeTab === "general" && <GeneralSection isDefaultAdmin={isDefaultAdmin} />}
      {activeTab === "users" && isAdmin && <AccountsSection />}
      {activeTab === "channels" && isAdmin && <AdminAlertChannelsSection />}
      {activeTab === "alerts" && <AlertConfigsSection />}
    </div>
  );
}
