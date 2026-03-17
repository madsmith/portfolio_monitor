import { useState } from "react";
import type { PortfolioSummary } from "../api/client";
import { fmtMoney, fmtPct, fmtChg, plColor, type TodayChange } from "../lib/formatters";

type SortKey = "name" | "value" | "todayChg" | "pl" | "costBasis";

export function Overview({
  portfolios,
  loading,
  error,
  onSelect,
  todayChange,
}: {
  portfolios: PortfolioSummary[];
  loading: boolean;
  error: string | null;
  onSelect: (id: string) => void;
  todayChange: Record<string, TodayChange>;
}) {
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  if (loading) return <p className="text-slate-500 py-2 text-sm">Loading…</p>;
  if (error) return <p className="text-red-400 py-2 text-sm">{error}</p>;
  if (portfolios.length === 0) return <p className="text-slate-500 py-2 text-sm">No portfolios found.</p>;

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "name" ? "asc" : "desc");
    }
  }

  const nullLast = (v: number | null, dir: "asc" | "desc") => v ?? (dir === "asc" ? Infinity : -Infinity);

  const sorted = sortKey === null ? portfolios : [...portfolios].sort((a, b) => {
    const chgA = todayChange[a.id] ?? null;
    const chgB = todayChange[b.id] ?? null;
    let cmp = 0;
    switch (sortKey) {
      case "name":      cmp = a.name.localeCompare(b.name); break;
      case "value":     cmp = nullLast(a.total_value, sortDir) - nullLast(b.total_value, sortDir); break;
      case "todayChg":  cmp = nullLast(chgA?.value ?? null, sortDir) - nullLast(chgB?.value ?? null, sortDir); break;
      case "pl":        cmp = nullLast(a.total_profit_loss, sortDir) - nullLast(b.total_profit_loss, sortDir); break;
      case "costBasis": cmp = nullLast(a.total_cost_basis, sortDir) - nullLast(b.total_cost_basis, sortDir); break;
    }
    return sortDir === "asc" ? cmp : -cmp;
  });

  function SortIcon({ k }: { k: SortKey }) {
    if (sortKey !== k) return <span className="text-slate-700 ml-0.5">⇅</span>;
    return <span className="text-slate-300 ml-0.5">{sortDir === "asc" ? "↑" : "↓"}</span>;
  }

  const cols: { label: string; align: string; vis: string; sk: SortKey | null }[] = [
    { label: "Portfolio",   align: "text-left",  vis: "",                     sk: "name"      },
    { label: "Value",       align: "text-right", vis: "",                     sk: "value"     },
    { label: "Today's Chg", align: "text-right", vis: "",                     sk: "todayChg"  },
    { label: "P&L",         align: "text-right", vis: "hidden md:table-cell", sk: "pl"        },
    { label: "Cost Basis",  align: "text-right", vis: "hidden lg:table-cell", sk: "costBasis" },
    { label: "",            align: "",           vis: "",                     sk: null        },
  ];

  return (
    <table className="w-full text-sm border-collapse">
      <thead>
        <tr>
          {cols.map(({ label, align, vis, sk }) => (
            <th
              key={label}
              onClick={() => sk && handleSort(sk)}
              className={[
                align, vis,
                "text-[0.7rem] uppercase tracking-wide text-slate-500 font-semibold px-3 py-2 border-b border-[#404868]",
                sk ? "cursor-pointer hover:text-slate-300 select-none" : "",
              ].join(" ")}
            >
              {sk ? (
                <span className={`inline-flex items-center ${align === "text-right" ? "justify-end" : ""}`}>
                  {label}
                  <SortIcon k={sk} />
                </span>
              ) : label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sorted.map((p) => {
          const chg = todayChange[p.id] ?? null;
          return (
            <tr
              key={p.id}
              onClick={() => onSelect(p.id)}
              className="border-b border-[#2a2d3a] hover:bg-[#252a40] cursor-pointer transition-colors last:border-b-0"
            >
              <td className="px-3 py-3 font-semibold text-slate-100">{p.name}</td>
              <td className="px-3 py-3 text-right tabular-nums text-slate-300">{fmtMoney(p.total_value)}</td>
              <td className={`px-3 py-3 text-right tabular-nums ${plColor(chg?.value ?? null)}`}>
                {chg ? (
                  <>
                    {fmtChg(chg.value)}
                    <span className="hidden sm:inline"> ({fmtPct(chg.pct)})</span>
                  </>
                ) : "—"}
              </td>
              <td className={`hidden md:table-cell px-3 py-3 text-right tabular-nums font-medium ${plColor(p.total_profit_loss)}`}>
                {fmtMoney(p.total_profit_loss)} ({fmtPct(p.profit_loss_percentage)})
              </td>
              <td className="hidden lg:table-cell px-3 py-3 text-right tabular-nums text-slate-300">{fmtMoney(p.total_cost_basis)}</td>
              <td className="px-3 py-3 text-right text-slate-600 text-base">→</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
