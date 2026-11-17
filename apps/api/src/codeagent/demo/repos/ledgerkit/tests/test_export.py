from ledgerkit.export import invoice_to_csv, render_text
from ledgerkit.invoice import Invoice
from ledgerkit.money import Money


def make_invoice():
    invoice = Invoice(customer="Acme Robotics", region="DE")
    invoice.add_line("Pick-and-place arm", 2, Money.of("1249.50"))
    return invoice


def test_csv_has_a_header_and_one_row_per_line():
    rows = invoice_to_csv(make_invoice()).splitlines()
    assert rows[0] == "description,quantity,unit_price,amount,currency"
    assert rows[1] == "Pick-and-place arm,2,1249.50,2499.00,EUR"


def test_text_receipt_lists_items_and_totals():
    text = render_text(make_invoice())
    assert text.startswith("Invoice for Acme Robotics")
    assert "Pick-and-place arm" in text
    assert "Total" in text
