import { ZodError, type ZodType } from "zod";
import type { AxiosResponse } from "axios";

/**
 * Thrown when a backend response fails Zod schema validation.
 *
 * Carries the raw response body and the request URL so the global query-error
 * handler can build a copy-pasteable bug report (path, code, message,
 * received value) instead of a silent toast.
 */
export class SchemaParseError extends Error {
  readonly zodError: ZodError;
  readonly responseData: unknown;
  readonly requestUrl: string;
  readonly requestMethod: string;

  constructor(
    zodError: ZodError,
    responseData: unknown,
    requestUrl: string,
    requestMethod: string,
  ) {
    super(`Schema parse failed for ${requestMethod} ${requestUrl}`);
    this.name = "SchemaParseError";
    this.zodError = zodError;
    this.responseData = responseData;
    this.requestUrl = requestUrl;
    this.requestMethod = requestMethod;
  }
}

/**
 * Axios-response transformer: validates `r.data` against the given Zod schema,
 * re-throwing as SchemaParseError (with raw data + URL attached) on failure.
 *
 * Usage:
 *   apiClient.get("/foo").then(parseResp(FooSchema))
 */
export const parseResp =
  <T>(schema: ZodType<T>) =>
  (r: AxiosResponse): T => {
    try {
      return schema.parse(r.data);
    } catch (e) {
      if (e instanceof ZodError) {
        throw new SchemaParseError(
          e,
          r.data,
          r.config.url ?? "(no url)",
          (r.config.method ?? "GET").toUpperCase(),
        );
      }
      throw e;
    }
  };
