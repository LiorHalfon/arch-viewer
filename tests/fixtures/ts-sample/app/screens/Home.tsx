import type { Order } from "@/domain/types";
import { total } from "@/domain/order";

export default function Home({ order }: { order: Order }) {
  return <p>{total(order)}</p>;
}
