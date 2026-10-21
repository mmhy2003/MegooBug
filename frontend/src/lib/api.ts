export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface FetchOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    path: string,
    options: FetchOptions = {}
  ): Promise<T> {
    const { body, headers: customHeaders, ...rest } = options;

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(customHeaders as Record<string, string>),
    };

    const config: RequestInit = {
      credentials: "include",
      headers,
      ...rest,
    };

    if (body !== undefined) {
      config.body = JSON.stringify(body);
    }

    const response = await fetch(`${this.baseUrl}${path}`, config);

    if (response.status === 401) {
      // Try to refresh the token
      const refreshResponse = await fetch(
        `${this.baseUrl}/api/v1/auth/refresh`,
        {
          method: "POST",
          credentials: "include",
        }
      );

      if (refreshResponse.ok) {
        // Retry the original request
        const retryResponse = await fetch(`${this.baseUrl}${path}`, config);
        if (!retryResponse.ok) {
          const retryBody = await retryResponse.json().catch(() => ({}));
          throw new ApiError(
            retryResponse.status,
            errorMessage(retryBody.detail, retryResponse.statusText)
          );
        }
        return retryResponse.json();
      }

      // Redirect to login, preserving current path for redirect-back
      if (typeof window !== "undefined") {
        const currentPath = window.location.pathname;
        window.location.href = `/login?redirect=${encodeURIComponent(currentPath)}`;
      }
      throw new ApiError(401, "Session expired");
    }

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      throw new ApiError(
        response.status,
        errorMessage(errorBody.detail, response.statusText)
      );
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return response.json();
  }

  get<T>(path: string, options?: FetchOptions) {
    return this.request<T>(path, { ...options, method: "GET" });
  }

  post<T>(path: string, body?: unknown, options?: FetchOptions) {
    return this.request<T>(path, { ...options, method: "POST", body });
  }

  patch<T>(path: string, body?: unknown, options?: FetchOptions) {
    return this.request<T>(path, { ...options, method: "PATCH", body });
  }

  put<T>(path: string, body?: unknown, options?: FetchOptions) {
    return this.request<T>(path, { ...options, method: "PUT", body });
  }

  delete<T>(path: string, options?: FetchOptions) {
    return this.request<T>(path, { ...options, method: "DELETE" });
  }
}

/**
 * Turn a FastAPI error `detail` into a readable message. Validation errors
 * (422) carry a list of `{msg, ...}` entries instead of a string.
 */
function errorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const msg = (detail[0] as { msg?: unknown })?.msg;
    if (typeof msg === "string" && msg) return msg.replace(/^Value error, /, "");
  }
  return fallback;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

export const api = new ApiClient(API_URL);
