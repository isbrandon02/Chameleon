import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiBase = env.VITE_API_BASE ?? "";
  if (!apiBase || apiBase.includes("elasticbeanstalk.com")) {
    throw new Error(
      "\n\nVITE_API_BASE is missing or points directly to the EB URL.\n" +
      "Create frontend/.env with:\n" +
      "  VITE_API_BASE=https://uw88poluwh.execute-api.us-east-1.amazonaws.com\n\n"
    );
  }
  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    base: "/",
  };
});
