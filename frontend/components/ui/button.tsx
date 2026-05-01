import { ButtonHTMLAttributes } from "react";
import clsx from "clsx";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "outline" | "ghost";
  size?: "sm" | "md" | "icon";
};

export function Button({
  className,
  variant = "outline",
  size = "md",
  ...props
}: ButtonProps) {
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg border text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" &&
          "border-moss-700 bg-moss-700 text-white shadow-sm hover:bg-moss-800",
        variant === "outline" &&
          "border-slate-200 bg-white text-slate-900 hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100",
        variant === "ghost" &&
          "border-transparent bg-transparent text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
        size === "sm" && "h-8 px-3",
        size === "md" && "h-11 px-4",
        size === "icon" && "h-10 w-10 p-0",
        className
      )}
      {...props}
    />
  );
}
