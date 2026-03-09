"""
Shared display utilities for CLI commands.

Provides:
  - ColumnMeta: field-level display metadata annotation for Pydantic models
  - fmt_value: format a single value according to a ColumnMeta fmt directive
  - render_table: print an aligned table from a list of Pydantic model instances
  - model_to_dict: serialize a model to dict with numeric fields rounded by fmt

Usage::

    from typing import Annotated
    from pydantic import BaseModel
    from portfolio_monitor.cli.display import ColumnMeta, fmt_value, render_table, model_to_dict

    class MyRow(BaseModel):
        name: Annotated[str, ColumnMeta("Name")]
        value: Annotated[float | None, ColumnMeta("Value", fmt="currency")]
        notes: Annotated[str | None, ColumnMeta("Notes", json_only=True)]

    render_table(rows)          # table: Name + Value only (notes skipped)
    model_to_dict(row)          # dict: all three fields, value rounded per currency precision
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import typing

from pydantic import BaseModel

from portfolio_monitor.core.currency import Currency, CurrencyType

__all__ = ["ColumnMeta", "fmt_value", "model_to_dict", "render_table"]

_RIGHT_ALIGNED_FORMATS = {"right", "currency", "percent", "change", "volume"}
_PERCENT_PRECISION = 2

# ---------------------------------------------------------------------------
# ColumnMeta — per-field display metadata
# ---------------------------------------------------------------------------

@dataclass
class ColumnMeta:
    title: str
    json_only: bool = False
    fmt: str = "left"  # left | right | currency | percent | change | volume
    min_width: int = 0
    currency_type: str | None = None  # e.g. "USD", "BTC" — used for json rounding precision


# ---------------------------------------------------------------------------
# Value formatter
# ---------------------------------------------------------------------------



def fmt_value(value: object, fmt: str) -> str:
    """Format a single value according to its ColumnMeta fmt directive.

    Returns an em-dash for None values.
    """
    if value is None:
        return "\u2014"  # —

    v = float(value) if fmt in _RIGHT_ALIGNED_FORMATS else value  # type: ignore[arg-type]

    if fmt == "currency":
        return f"${v:,.2f}"
    if fmt == "change":
        assert isinstance(v, (int, float)), "Format 'change' requires numeric value"
        sign = "+" if v >= 0 else ""
        return f"{sign}${v:,.2f}"
    if fmt == "percent":
        assert isinstance(v, (int, float)), "Format 'percent' requires numeric value"
        sign = "+" if v >= 0 else ""
        return f"{sign}{v:.2f}%"
    if fmt == "volume":
        assert isinstance(v, (int, float)), "Format 'volume' requires numeric value"
        return f"{v:,.2f}"

    # left / right — plain string
    return str(value)


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

def _all_col_specs(model_cls: type[BaseModel]) -> list[tuple[str, ColumnMeta]]:
    """Return [(field_name, ColumnMeta), ...] in declaration order, including json_only fields."""
    hints = typing.get_type_hints(model_cls, include_extras=True)
    specs: list[tuple[str, ColumnMeta]] = []
    for field_name, hint in hints.items():
        if typing.get_origin(hint) is not typing.Annotated:
            continue
        for arg in typing.get_args(hint)[1:]:
            if isinstance(arg, ColumnMeta):
                specs.append((field_name, arg))
                break
    return specs


def _col_specs(model_cls: type[BaseModel]) -> list[tuple[str, ColumnMeta]]:
    """Return [(field_name, ColumnMeta), ...] in declaration order, skipping json_only fields."""
    return [(n, m) for n, m in _all_col_specs(model_cls) if not m.json_only]


# ---------------------------------------------------------------------------
# JSON serializer with rounding
# ---------------------------------------------------------------------------



def _json_precision(meta: ColumnMeta) -> int | None:
    """Return the number of decimal places to use when serializing a field to JSON."""
    if meta.fmt == "percent":
        return _PERCENT_PRECISION
    if meta.fmt in ("currency", "change"):
        ct = CurrencyType[meta.currency_type] if meta.currency_type else Currency.DEFAULT_CURRENCY_TYPE
        return ct.config.precision
    return None


def model_to_dict(model: BaseModel) -> dict:
    """Serialize a model to a dict, rounding numeric fields based on their fmt.

    - percent fields: rounded to 2dp
    - currency/change fields: rounded to the precision of their declared currency_type
      (defaults to Currency.DEFAULT_CURRENCY_TYPE, i.e. USD = 2dp)
    All fields (including json_only) are included.
    """
    data = model.model_dump()
    for field_name, meta in _all_col_specs(type(model)):
        precision = _json_precision(meta)
        if precision is not None and isinstance(data.get(field_name), float):
            data[field_name] = round(data[field_name], precision)
    return data


# ---------------------------------------------------------------------------
# Table renderer
# ---------------------------------------------------------------------------

def render_table(rows: Sequence[BaseModel], *, indent: str = "") -> None:
    """Print an aligned table for a list of Pydantic model instances.

    Only fields annotated with ColumnMeta(json_only=False) are rendered.
    Column order follows field declaration order.
    Right-aligned fmts: right, currency, percent, change.
    Column separator: two spaces.
    """
    if not rows:
        return

    column_margin = 4
    specs = _col_specs(type(rows[0]))
    if not specs:
        return

    formatted: list[list[str]] = [
        [fmt_value(getattr(row, name), meta.fmt) for name, meta in specs]
        for row in rows
    ]

    headers = [meta.title for _, meta in specs]
    widths = [
        max(len(headers[i]), specs[i][1].min_width, *(len(formatted[r][i]) for r in range(len(rows))))
        for i in range(len(specs))
    ]

    def _render_row(cells: list[str]) -> str:
        parts = [
            f"{c:>{w}}" if specs[i][1].fmt in _RIGHT_ALIGNED_FORMATS else f"{c:<{w}}"
            for i, (c, w) in enumerate(zip(cells, widths))
        ]
        return (indent + (" " * column_margin).join(parts)).rstrip()

    print(_render_row(headers))
    print(indent + ("-" * column_margin).join("-" * w for w in widths))
    for row_cells in formatted:
        print(_render_row(row_cells))
