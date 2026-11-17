/** Prices are integer cents everywhere; floats only appear when formatting. */
export type Cents = number;

export const CURRENCY = "EUR";

/** Format integer cents as a localized price, for example "EUR 1,249.50". */
export function formatPrice(cents: Cents, currency: string = CURRENCY): string {
  const value = (cents / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${currency} ${value}`;
}

/** Round half away from zero, the way receipts round. */
export function roundCents(value: number): Cents {
  return Math.sign(value) * Math.round(Math.abs(value));
}
