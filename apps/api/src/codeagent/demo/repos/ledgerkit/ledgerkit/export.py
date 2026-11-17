"""Export invoices as CSV rows or a plain-text receipt."""

from __future__ import annotations

import csv
import io

from ledgerkit.invoice import Invoice
from ledgerkit.tax import tax_breakdown

CSV_HEADER = ("description", "quantity", "unit_price", "amount", "currency")


def invoice_to_rows(invoice: Invoice) -> list[tuple[str, ...]]:
    return [
        (
            line.description,
            str(line.quantity),
            f"{line.unit_price.amount:.2f}",
            f"{line.amount().amount:.2f}",
            invoice.currency,
        )
        for line in invoice.lines
    ]


def invoice_to_csv(invoice: Invoice) -> str:
    """The invoice lines as CSV with a header row, ready for a spreadsheet."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    writer.writerows(invoice_to_rows(invoice))
    return buffer.getvalue()


def render_text(invoice: Invoice) -> str:
    """A receipt for terminals and emails: one line per item, then the totals."""
    lines = [f"Invoice for {invoice.customer}", ""]
    for line in invoice.lines:
        lines.append(f"{line.quantity:>4} x {line.description:<28} {line.amount().format():>16}")
    summary = tax_breakdown(invoice.discounted_subtotal(), invoice.region)
    lines += ["", f"Subtotal {summary['subtotal']:>40}", f"Tax ({summary['rate']}) {summary['tax']:>33}"]
    lines.append(f"Total {summary['total']:>43}")
    return "\n".join(lines)
