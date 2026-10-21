import {
  startAuthentication,
  startRegistration,
  type PublicKeyCredentialCreationOptionsJSON,
  type PublicKeyCredentialRequestOptionsJSON,
} from "@simplewebauthn/browser";
import { api } from "@/lib/api";
import type { CurrentUser } from "@/components/current-user-provider";

export { isMfaChallenge, type MfaChallenge, type MfaMethod } from "@/lib/mfa-challenge";

export interface TotpSetup {
  secret: string;
  otpauth_uri: string;
}

/** Shown by the backend when the pending sign-in is gone; restart at the password. */
export const SIGN_IN_EXPIRED = "Your sign-in expired. Enter your password again.";

export function verifyLoginTotp(code: string): Promise<CurrentUser> {
  return api.post<CurrentUser>("/api/v1/auth/2fa/totp", { code });
}

export async function verifyLoginPasskey(): Promise<CurrentUser> {
  const optionsJSON = await api.post<PublicKeyCredentialRequestOptionsJSON>(
    "/api/v1/auth/2fa/passkey/options"
  );
  const credential = await startAuthentication({ optionsJSON });
  return api.post<CurrentUser>("/api/v1/auth/2fa/passkey", { credential });
}

/**
 * Register a passkey: fetch creation options from `optionsPath` (with an
 * optional body, e.g. the current password), run the browser ceremony, then
 * post the result to `finishPath`.
 */
export async function registerPasskey<T>(
  optionsPath: string,
  finishPath: string,
  name: string,
  optionsBody?: unknown
): Promise<T> {
  const optionsJSON = await api.post<PublicKeyCredentialCreationOptionsJSON>(
    optionsPath,
    optionsBody
  );
  const credential = await startRegistration({ optionsJSON });
  return api.post<T>(finishPath, { credential, name });
}

/** A readable default passkey name from the browser and OS, e.g. "Chrome on Windows". */
export function defaultPasskeyName(): string {
  if (typeof navigator === "undefined") return "Passkey";
  const ua = navigator.userAgent;
  const browser = /Edg\//.test(ua)
    ? "Edge"
    : /Firefox\//.test(ua)
      ? "Firefox"
      : /Chrome\//.test(ua)
        ? "Chrome"
        : /Safari\//.test(ua)
          ? "Safari"
          : "Browser";
  const os = /Windows/.test(ua)
    ? "Windows"
    : /Android/.test(ua)
      ? "Android"
      : /iPhone|iPad/.test(ua)
        ? "iOS"
        : /Mac OS X/.test(ua)
          ? "macOS"
          : /Linux/.test(ua)
            ? "Linux"
            : "";
  return os ? `${browser} on ${os}` : browser;
}

/** Group a base32 secret in fours for reading: "JBSW Y3DP EHPK 3PXP". */
export function groupSecret(secret: string): string {
  return secret.replace(/(.{4})/g, "$1 ").trim();
}

/** Errors from the WebAuthn ceremony (user cancelled, timed out…) as a message. */
export function passkeyErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error && err.name === "NotAllowedError") {
    return "The passkey prompt was cancelled or timed out.";
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}
