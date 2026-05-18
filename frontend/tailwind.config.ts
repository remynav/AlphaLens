import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#17211f",
        moss: "#50665c",
        paper: "#f7f7f2",
        brass: "#b98f4b",
        signal: "#2563eb",
      },
      boxShadow: {
        panel: "0 18px 45px rgba(23, 33, 31, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
