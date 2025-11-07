import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: "#16a34a", // green-600 to match background gradient
          dark: "#0F172A",
        },
      },
    },
  },
  plugins: [],
};

export default config;
