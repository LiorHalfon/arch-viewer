import {
  useMutation,
  useQuery,
} from "@tanstack/react-query";

interface Props {
  label: string;
}

function legacyIcon() {
  require("@/assets/icon.png");
  return require("../utils/legacy.js");
}

export function Button({ label }: Props) {
  useQuery({ queryKey: [label] });
  useMutation({ mutationKey: [label] });
  return (
    <button>
      {label}
      {legacyIcon()}
    </button>
  );
}
