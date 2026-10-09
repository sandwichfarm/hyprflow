import { test } from "node:test";
import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { setupCheckpoint } from "./setup-checkpoint.mjs";

test("resume files are scoped to repo and environment, and exclude unrelated env vars", (t) => {
  const directory = mkdtempSync(join(tmpdir(), "bunny-checkpoint-test-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const checkpoint = setupCheckpoint(directory, { repo: "owner/site", environment: "production" });
  checkpoint.save({ BUNNY_API_KEY: "private-value", UNRELATED_SECRET: "not-bunny" });
  assert.deepEqual(checkpoint.load(), { BUNNY_API_KEY: "private-value" });
  for (const scope of [
    { repo: "owner/other", environment: "production" },
    { repo: "owner/site", environment: "staging" },
  ]) assert.deepEqual(setupCheckpoint(directory, scope).load(), {});
  assert.ok(!readFileSync(checkpoint.path, "utf8").includes("not-bunny"));
  chmodSync(checkpoint.path, 0o644);
  assert.throws(() => checkpoint.load(), /accessible only to you/);
});

test("unsafe or corrupt resume files fail without exposing their contents", (t) => {
  const directory = mkdtempSync(join(tmpdir(), "bunny-checkpoint-test-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const scope = { repo: "owner/site", environment: "production" };
  const checkpoint = setupCheckpoint(directory, scope);
  writeFileSync(checkpoint.path, '{"BUNNY_API_KEY":"private-value', { mode: 0o600 });
  assert.throws(() => checkpoint.load(), (error) => /Cannot read setup resume/.test(error.message) && !error.message.includes("private-value"));
  checkpoint.clear();
  const target = join(directory, "target");
  writeFileSync(target, "private-value", { mode: 0o600 });
  symlinkSync(target, checkpoint.path);
  assert.throws(() => checkpoint.load(), { code: "ELOOP" });
  assert.equal(readFileSync(target, "utf8"), "private-value");
  const link = join(directory, "linked-directory");
  symlinkSync(directory, link);
  assert.throws(() => setupCheckpoint(link, scope).load(), /must not be a symlink/);
});
