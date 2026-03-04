import type { PortfolioSummary } from "../api/client";
import { fmtMoney, fmtPct, fmtChg, plColor, type TodayChange } from "../lib/formatters";

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

  return (
    <table className="w-full text-sm border-collapse">
      <thead>
        <tr>
          {(
            [
              ["Portfolio", "text-left"],
              ["Value", "text-right"],
              ["Today's Chg", "text-right"],
              ["Cost Basis", "text-right"],
              ["P&L", "text-right"],
              ["", ""],
            ] as [string, string][]
          ).map(([label, align], i) => (
            <th
              key={i}
              className={`${align} text-[0.7rem] uppercase tracking-wide text-slate-500 font-semibold px-3 py-2 border-b border-[#404868]`}
            >
              {label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {portfolios.map((p) => {
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
                {chg ? `${fmtChg(chg.value)} (${fmtPct(chg.pct)})` : "—"}
              </td>
              <td className="px-3 py-3 text-right tabular-nums text-slate-300">{fmtMoney(p.total_cost_basis)}</td>
              <td className={`px-3 py-3 text-right tabular-nums font-medium ${plColor(p.total_profit_loss)}`}>
                {fmtMoney(p.total_profit_loss)} ({fmtPct(p.profit_loss_percentage)})
              </td>
              <td className="px-3 py-3 text-right text-slate-600 text-base">→</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
