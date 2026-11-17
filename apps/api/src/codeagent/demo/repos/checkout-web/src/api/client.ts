import type { CartLine } from "../cart";

export interface Product {
  sku: string;
  name: string;
  unitPrice: number;
  inStock: boolean;
}

export interface OrderReceipt {
  orderId: string;
  totalCents: number;
}

const API_BASE = "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!response.ok) throw new Error(`request failed: ${response.status}`);
  return (await response.json()) as T;
}

/** Products available for the storefront, in stock first. */
export async function fetchProducts(): Promise<Product[]> {
  const products = await request<Product[]>("/products");
  return products.sort((a, b) => Number(b.inStock) - Number(a.inStock));
}

/** Submit the cart lines as an order; the server recomputes every price. */
export async function submitOrder(lines: CartLine[], couponCode?: string): Promise<OrderReceipt> {
  return request<OrderReceipt>("/orders", {
    method: "POST",
    body: JSON.stringify({ lines: lines.map(({ sku, quantity }) => ({ sku, quantity })), couponCode }),
  });
}
