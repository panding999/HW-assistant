import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        ink: "#111827",
        muted: "#667085",
        moss: {
          50: "#eef8f3",
          100: "#d9efe5",
          600: "#0f6f57",
          700: "#0b5947",
          800: "#064536"
        }
      },
      boxShadow: {
        soft: "0 10px 30px rgba(17, 24, 39, 0.06)"
      }
    }
  },
  plugins: []
};

export default config;
