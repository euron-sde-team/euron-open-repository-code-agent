import { formatPrice } from "../money";
import type { Cart } from "../cart";

/** The order summary shown next to the checkout form. */
export function CartSummary({ cart }: { cart: Cart }) {
  return (
    <aside className="cart-summary">
      <p>Subtotal: {formatPrice(cart.subtotal())}</p>
      <p className="total">Total: {formatPrice(cart.total())}</p>
    </aside>
  );
}
