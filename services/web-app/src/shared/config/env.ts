import { z } from "zod";

declare global {
  /* eslint-disable-next-line @typescript-eslint/consistent-type-definitions */
  interface Window {
    __APP_CONFIG__?: {
      API_BASE_URL: string;
      APP_ENV: string;
      BUILD_TIME: string;
      VERSION: string;
    };
  }
}

const runtimeBaseUrl =
  typeof window !== "undefined" && window.__APP_CONFIG__ != null
    ? window.__APP_CONFIG__.API_BASE_URL
    : "http://localhost:8000";

const runtimeAppEnv =
  typeof window !== "undefined" && window.__APP_CONFIG__?.APP_ENV
    ? window.__APP_CONFIG__.APP_ENV
    : "development";

const envSchema = z.object({
  VITE_API_BASE_URL: z
    .string()
    .default(runtimeBaseUrl)
    .describe("Backend base URL (without /api/v1 suffix)"),
  VITE_APP_ENV: z
    .enum(["development", "staging", "production"])
    .default(runtimeAppEnv as "development" | "staging" | "production")
    .describe("Application environment"),
});

const parseEnv = () => {
  try {
    return envSchema.parse(import.meta.env);
  } catch (error) {
    if (error instanceof z.ZodError) {
      console.error("Environment validation failed:", error);
      throw new Error("Invalid environment configuration", { cause: error });
    }
    throw error;
  }
};

export const env = parseEnv();

export const isDevelopment = env.VITE_APP_ENV === "development";
export const isProduction = env.VITE_APP_ENV === "production";
