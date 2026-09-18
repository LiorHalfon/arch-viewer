import type { Order } from "./types";
import { discount } from "@/services/pricing";

export function total(order: Order): number {
  return order.lines.reduce((sum, line) => sum + line, 0) - discount(order);
}
