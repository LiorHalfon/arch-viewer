export interface Order {
  id: string;
  lines: number[];
}

export type OrderId = Order["id"];
