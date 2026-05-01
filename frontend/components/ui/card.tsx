import { HTMLAttributes } from "react";
import clsx from "clsx";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={clsx(
        "rounded-lg border border-slate-200 bg-white shadow-soft dark:border-slate-800 dark:bg-slate-900",
        className
      )}
      {...props}
    />
  );
}
