import { formatPrice, type Cents } from "./money";
import { applyCoupon, type Coupon } from "./pricing";

export interface CartLine {
  sku: string;
  name: string;
  unitPrice: Cents;
  quantity: number;
}

/** The shopping cart: lines keyed by SKU, an optional coupon and derived totals. */
export class Cart {
  private lines = new Map<string, CartLine>();
  private coupon: Coupon | null = null;

  addItem(line: CartLine): void {
    const existing = this.lines.get(line.sku);
    if (existing) {
      existing.quantity += line.quantity;
      return;
    }
    this.lines.set(line.sku, { ...line });
  }

  removeItem(sku: string): boolean {
    return this.lines.delete(sku);
  }

  setQuantity(sku: string, quantity: number): void {
    const line = this.lines.get(sku);
    if (!line) throw new Error(`unknown SKU ${sku}`);
    if (quantity <= 0) {
      this.removeItem(sku);
      return;
    }
    line.quantity = quantity;
  }

  useCoupon(coupon: Coupon | null): void {
    this.coupon = coupon;
  }

  subtotal(): Cents {
    let total = 0;
    for (const line of this.lines.values()) total += line.unitPrice * line.quantity;
    return total;
  }

  total(): Cents {
    return applyCoupon(this.subtotal(), this.coupon);
  }

  summary(): string {
    return `${this.lines.size} item(s), ${formatPrice(this.total())}`;
  }
}
