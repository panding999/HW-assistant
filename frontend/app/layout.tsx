import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FZU Homework Assistant",
  description: "AI 作业资料与实验报告工作台"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
