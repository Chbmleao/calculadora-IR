import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server on 5173 (README §3). API base URL is read at runtime from
// import.meta.env.VITE_API_BASE_URL (see src/api/client.ts).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
});
