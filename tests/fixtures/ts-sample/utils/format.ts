import { readFileSync } from "fs";
import path from "node:path";
import { nope } from "@/utils/missing";

export function format(value: number): string {
  return `${value}${path.sep}${readFileSync.name}${nope}`;
}
