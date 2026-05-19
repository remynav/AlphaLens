import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#101413",
        charcoal: "#1d2421",
        moss: "#56645f",
        paper: "#f3f0e8",
        bone: "#fbfaf6",
        line: "#d9d4c8",
        brass: "#a9792b",
        signal: "#2057ff",
        mint: "#9ff0c2",
      },
      boxShadow: {
        panel: "0 18px 50px rgba(16, 20, 19, 0.08)",
        inset: "inset 0 1px 0 rgba(255, 255, 255, 0.55)",
      },
    },
  },
  plugins: [],
};

export default config;
