import type { Order } from "./types";

export abstract class Repository {
  abstract find(id: string): Order | undefined;
}
