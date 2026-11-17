"""`python -m ledgerkit.cli total --region DE 2x1249.50 1x180`: quick totals from a shell."""

from __future__ import annotations

import argparse

from ledgerkit.invoice import Invoice
from ledgerkit.money import Money


def parse_item(text: str) -> tuple[int, Money]:
    quantity, _, price = text.partition("x")
    return int(quantity), Money.of(price)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ledgerkit")
    commands = parser.add_subparsers(dest="command", required=True)
    total = commands.add_parser("total", help="print an invoice total")
    total.add_argument("--region", default="DE")
    total.add_argument("items", nargs="+", help="QUANTITYxPRICE, for example 2x1249.50")
    args = parser.parse_args(argv)

    invoice = Invoice(customer="cli", region=args.region)
    for index, item in enumerate(args.items, start=1):
        quantity, price = parse_item(item)
        invoice.add_line(f"item {index}", quantity, price)
    print(invoice.total())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
