import type { ButtonHTMLAttributes } from "react";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary";
};

export function Button({ variant = "primary", children, ...props }: ButtonProps) {
  const classes =
    variant === "primary"
      ? "rounded-sm bg-accent px-4 py-2 text-sm font-semibold text-on-accent disabled:cursor-not-allowed disabled:opacity-60"
      : "rounded-sm border border-border px-3 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60";

  return (
    <button {...props} className={classes}>
      {children}
    </button>
  );
}
