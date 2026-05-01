import React, { useState } from "react";

export interface ColDef<T> {
  key: string;
  label: string;
  align?: "left" | "right";
  /** Tailwind responsive visibility class, e.g. "hidden md:table-cell" */
  vis?: string;
  /** Return the value used for sorting; omit to make the column non-sortable */
  sortValue?: (row: T) => string | number | null;
  /** Sort direction when first clicking this column (default: "desc") */
  defaultDir?: "asc" | "desc";
  /** Badge text rendered inside the header (e.g. "$" / "%") */
  badge?: string;
  /** Called when the badge is clicked; does not trigger sort */
  onBadge?: () => void;
}

export function DataTable<T>({
  columns,
  rows,
  getKey,
  renderRow,
  footer,
}: {
  columns: ColDef<T>[];
  rows: T[];
  getKey: (row: T) => string;
  renderRow: (row: T) => React.ReactNode;
  footer?: React.ReactNode;
}) {
  const [sortColKey, setSortColKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  function handleSort(col: ColDef<T>) {
    if (sortColKey === col.key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortColKey(col.key);
      setSortDir(col.defaultDir ?? "desc");
    }
  }

  const activeCol = columns.find((c) => c.key === sortColKey);

  const sorted = !activeCol?.sortValue ? rows : [...rows].sort((a, b) => {
    const av = activeCol.sortValue!(a);
    const bv = activeCol.sortValue!(b);
    const fallback = sortDir === "asc" ? Infinity : -Infinity;
    const an = av ?? fallback;
    const bn = bv ?? fallback;
    const cmp =
      typeof an === "string" && typeof bn === "string"
        ? an.localeCompare(bn)
        : (an as number) - (bn as number);
    return sortDir === "asc" ? cmp : -cmp;
  });

  return (
    <table className="w-full text-sm border-collapse">
      <thead>
        <tr>
          {columns.map((col) => {
            const isSorted = sortColKey === col.key;
            const alignClass = col.align === "right" ? "text-right" : "text-left";
            return (
              <th
                key={col.key}
                onClick={() => col.sortValue && handleSort(col)}
                className={[
                  alignClass,
                  col.vis ?? "",
                  "text-[0.7rem] uppercase tracking-wide text-slate-500 font-semibold px-2 sm:px-3 py-2 border-b border-[#404868]",
                  col.sortValue ? "cursor-pointer hover:text-slate-300 select-none" : "",
                ].join(" ")}
              >
                {col.sortValue ? (
                  <span className={`inline-flex items-center ${col.align === "right" ? "justify-end" : ""}`}>
                    {col.label}
                    {col.badge !== undefined && (
                      <span
                        onClick={(e) => { e.stopPropagation(); col.onBadge?.(); }}
                        className="ml-1 px-1 rounded bg-[#2a2d3a] text-slate-400 hover:text-slate-100 hover:bg-[#404868] cursor-pointer transition-colors normal-case tracking-normal font-normal"
                      >
                        {col.badge}
                      </span>
                    )}
                    {isSorted
                      ? <span className="text-slate-300 ml-0.5">{sortDir === "asc" ? "↑" : "↓"}</span>
                      : <span className="text-slate-700 ml-0.5">⇅</span>
                    }
                  </span>
                ) : col.label}
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {sorted.map((row) => (
          <React.Fragment key={getKey(row)}>
            {renderRow(row)}
          </React.Fragment>
        ))}
        {footer}
      </tbody>
    </table>
  );
}
