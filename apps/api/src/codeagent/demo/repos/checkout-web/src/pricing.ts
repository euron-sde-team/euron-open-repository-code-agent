import { roundCents, type Cents } from "./money";

export interface Coupon {
  code: string;
  percentOff?: number;
  amountOff?: Cents;
  minimumSubtotal?: Cents;
}

export const MAX_PERCENT_OFF = 50;

/** The discount a coupon gives on a subtotal; never more than the subtotal itself. */
export function couponDiscount(subtotal: Cents, coupon: Coupon): Cents {
  if (coupon.minimumSubtotal !== undefined && subtotal < coupon.minimumSubtotal) {
    return 0;
  }
  if (coupon.percentOff !== undefined) {
    const percent = Math.min(coupon.percentOff, MAX_PERCENT_OFF);
    return roundCents((subtotal * percent) / 100);
  }
  return Math.min(coupon.amountOff ?? 0, subtotal);
}

/** Subtotal after the coupon, as integer cents. */
export const applyCoupon = (subtotal: Cents, coupon: Coupon | null): Cents =>
  coupon ? subtotal - couponDiscount(subtotal, coupon) : subtotal;
