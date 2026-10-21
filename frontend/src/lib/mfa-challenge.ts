// Kept free of imports so it can be unit-tested with plain `node --test`.

export type MfaMethod = "passkey" | "totp";

/** Login accepted the password; a second step (or forced setup) comes next. */
export interface MfaChallenge {
  mfa_required: "verify" | "setup";
  methods: MfaMethod[];
  email: string;
}

/**
 * Users also carry a boolean `mfa_required`, so check the value: only a
 * challenge has "verify" or "setup".
 */
export function isMfaChallenge(x: unknown): x is MfaChallenge {
  if (typeof x !== "object" || x === null) return false;
  const kind = (x as { mfa_required?: unknown }).mfa_required;
  return kind === "verify" || kind === "setup";
}
