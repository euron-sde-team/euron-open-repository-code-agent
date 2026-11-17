# ledgerkit

Small, exact money arithmetic for invoices: amounts in `Decimal`, tax by region, volume and
threshold discounts, and CSV or plain-text export.

```python
from decimal import Decimal
from ledgerkit import Invoice, Money

invoice = Invoice(customer="Acme Robotics", region="DE")
invoice.add_line("Pick-and-place arm", quantity=2, unit_price=Money.of("1249.50"))
invoice.add_line("Service plan", quantity=1, unit_price=Money.of("180.00"))
print(invoice.total())          # EUR 3,028.61: 5% off orders over 1,000, then 19% VAT
```

## Development

```bash
python -m pytest -q
```
