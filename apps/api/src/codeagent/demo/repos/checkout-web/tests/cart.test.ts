import { describe, expect, it } from "vitest";

import { Cart } from "../src/cart";

describe("Cart", () => {
  it("merges lines with the same SKU", () => {
    const cart = new Cart();
    cart.addItem({ sku: "ARM-2", name: "Arm", unitPrice: 124950, quantity: 1 });
    cart.addItem({ sku: "ARM-2", name: "Arm", unitPrice: 124950, quantity: 1 });
    expect(cart.subtotal()).toBe(249900);
  });

  it("applies a percentage coupon", () => {
    const cart = new Cart();
    cart.addItem({ sku: "PAD-1", name: "Pads", unitPrice: 400, quantity: 10 });
    cart.useCoupon({ code: "SPRING10", percentOff: 10 });
    expect(cart.total()).toBe(3600);
  });
});
