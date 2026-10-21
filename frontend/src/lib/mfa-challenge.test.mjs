// Run: node --test --experimental-strip-types src/lib/mfa-challenge.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { isMfaChallenge } from "./mfa-challenge.ts";

test("a 2FA challenge is recognised", () => {
  assert.equal(isMfaChallenge({ mfa_required: "verify", methods: ["totp"], email: "a@b.c" }), true);
  assert.equal(isMfaChallenge({ mfa_required: "setup", methods: [], email: "a@b.c" }), true);
});

test("a normal login user (mfa_required: false) is not a challenge", () => {
  const user = { id: "1", email: "a@b.c", mfa_required: false, mfa_methods: [] };
  assert.equal(isMfaChallenge(user), false);
});

test("a user an admin requires 2FA of, with methods, is not a challenge", () => {
  assert.equal(isMfaChallenge({ id: "1", mfa_required: true, mfa_methods: ["totp"] }), false);
});

test("non-objects are not challenges", () => {
  assert.equal(isMfaChallenge(null), false);
  assert.equal(isMfaChallenge("verify"), false);
});
