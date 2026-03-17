import type { PortfolioSummary } from "../api/client";
import { fmtMoney, fmtPct, fmtChg, plColor, type TodayChange } from "../lib/formatters";
import { DataTable, type ColDef } from "./DataTable";

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
  if (loading) return <p className="text-slate-500 py-2 text-sm">Loading…</p>;
  if (error) return <p className="text-red-400 py-2 text-sm">{error}</p>;
  if (portfolios.length === 0) return <p className="text-slate-500 py-2 text-sm">No portfolios found.</p>;

  const columns: ColDef<PortfolioSummary>[] = [
    { key: "name",      label: "Portfolio",   align: "left",  sortValue: (p) => p.name,              defaultDir: "asc" },
    { key: "value",     label: "Value",       align: "right", sortValue: (p) => p.total_value },
    { key: "todayChg",  label: "Today's Chg", align: "right", sortValue: (p) => todayChange[p.id]?.value ?? null },
    { key: "pl",        label: "P&L",         align: "right", sortValue: (p) => p.total_profit_loss,  vis: "hidden md:table-cell" },
    { key: "costBasis", label: "Cost Basis",  align: "right", sortValue: (p) => p.total_cost_basis,   vis: "hidden lg:table-cell" },
    { key: "arrow",     label: "" },
  ];

  return (
    <DataTable
      columns={columns}
      rows={portfolios}
      getKey={(p) => p.id}
      renderRow={(p) => {
        const chg = todayChange[p.id] ?? null;
        return (
          <tr
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
      }}
    />
  );
}
