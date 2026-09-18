import { total } from "@/domain/order";
import type { Order } from "@/domain/types";

export function discount(order: Order): number {
  return order.lines.length > 3 ? total({ ...order, lines: [] }) / 10 : 0;
}
