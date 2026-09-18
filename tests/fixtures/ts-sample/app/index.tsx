import { Button } from "@/components";
import { format } from "@/utils/format";

export const loadHome = () => import("@/app/screens/Home");

export function loadByName(name: string) {
  return import(name);
}

export default function App() {
  return <Button label={format(1)} />;
}
