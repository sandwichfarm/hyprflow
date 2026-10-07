import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { deploy, collectFiles, request } from "./deploy-bunny.mjs";
import { configFromEnv } from "./config.mjs";
import { applyConfig, parseArgs } from "./setup-bunny.mjs";
const env = {
  BUNNY_STORAGE_ZONE: "hyprflow",
  BUNNY_STORAGE_HOST: "ny.storage.bunnycdn.com",
  BUNNY_PULL_ZONE_ID: "123",
  BUNNY_PUBLIC_URL: "https://hyprflow.b-cdn.net",
  BUNNY_STORAGE_PASSWORD: "storage-secret",
  BUNNY_API_KEY: "purge-secret",
};
async function fixture(t) {
  const directory = await mkdtemp(join(tmpdir(), "hyprflow-deploy-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  await mkdir(join(directory, "docs/assets"), { recursive: true });
  for (const path of [
    "index.html",
    "docs/index.html",
    "docs/getting-started.html",
    "docs/assets/a file.js",
  ])
    await writeFile(join(directory, path), path);
  return directory;
}
test("upload assets before pages, preserve /docs, checksum bytes, then purge with separate key", async (t) => {
  const directory = await fixture(t);
  const calls = [];
  await deploy({
    directory,
    env,
    log: () => {},
    fetchImpl: async (url, options) => {
      calls.push({ url, ...options });
      return new Response("", { status: 201 });
    },
  });
  assert.equal(calls.length, 5);
  assert.match(calls[0].url, /\/hyprflow\/docs\/assets\/a%20file.js$/);
  assert.equal(calls[0].headers["Content-Type"], "application/javascript");
  assert.equal(calls[0].body.toString(), "docs/assets/a file.js");
  assert.match(calls[0].headers.Checksum, /^[A-F0-9]{64}$/);
  assert.ok(
    calls
      .slice(0, -1)
      .every(
        (c) =>
          c.method === "PUT" &&
          c.headers.AccessKey === "storage-secret" &&
          c.redirect === "error",
      ),
  );
  assert.equal(
    calls.at(-1).url,
    "https://api.bunny.net/pullzone/123/purgeCache",
  );
  assert.equal(calls.at(-1).headers.AccessKey, "purge-secret");
});
test("dry run needs no secrets and never makes network calls", async (t) => {
  const output = [];
  await deploy({
    directory: await fixture(t),
    env: {},
    dryRun: true,
    log: (s) => output.push(s),
    fetchImpl: () => assert.fail("network called"),
  });
  assert.ok(output.some((s) => s.includes("/docs/index.html")));
});
test("reject missing credentials, foreign storage hosts, invalid zone and non-root public URLs", () => {
  assert.throws(() => configFromEnv({}), /Missing/);
  for (const host of [
    "https://storage.bunnycdn.com",
    "evil.example",
    "storage.bunnycdn.com.evil.example",
  ])
    assert.throws(
      () => configFromEnv({ ...env, BUNNY_STORAGE_HOST: host }),
      /hostname/,
    );
  assert.throws(
    () => configFromEnv({ ...env, BUNNY_STORAGE_ZONE: "../elsewhere" }),
    /Invalid/,
  );
  assert.throws(
    () =>
      configFromEnv({ ...env, BUNNY_PUBLIC_URL: "https://example.com/docs" }),
    /origin/,
  );
});
test("reject incomplete build and symlinks before networking", async (t) => {
  const directory = await fixture(t);
  await symlink(join(directory, "index.html"), join(directory, "leak.html"));
  await assert.rejects(collectFiles(directory), /symbolic link/);
  await rm(join(directory, "leak.html"));
  await rm(join(directory, "docs/index.html"));
  await assert.rejects(collectFiles(directory), /Incomplete build/);
});
test("upload failure stops deployment before CDN purge and hides response body", async (t) => {
  const calls = [];
  await assert.rejects(
    deploy({
      directory: await fixture(t),
      env,
      log: () => {},
      fetchImpl: async (url) => {
        calls.push(url);
        return new Response("sensitive upstream response", { status: 401 });
      },
    }),
    { message: "Bunny request failed: HTTP 401." },
  );
  assert.equal(calls.length, 1);
});
test("retry transient failures but propagate exhausted retries and purge failure", async (t) => {
  let attempts = 0;
  await request(
    "https://storage.bunnycdn.com/",
    {},
    {
      sleep: async () => {},
      fetchImpl: async () =>
        new Response("", { status: ++attempts < 3 ? 503 : 200 }),
    },
  );
  assert.equal(attempts, 3);
  attempts = 0;
  await assert.rejects(
    request(
      "https://storage.bunnycdn.com/",
      {},
      {
        sleep: async () => {},
        fetchImpl: async () => {
          attempts++;
          throw new Error("secret");
        },
      },
    ),
    /3 attempts/,
  );
  assert.equal(attempts, 3);
  await assert.rejects(
    deploy({
      directory: await fixture(t),
      env,
      log: () => {},
      fetchImpl: async (url) =>
        new Response("", { status: url.includes("purgeCache") ? 403 : 201 }),
    }),
    /HTTP 403/,
  );
});
test("setup config uses environment scope and stdin for credentials; dry run performs no writes", () => {
  const calls = [],
    logs = [];
  const options = parseArgs(["--repo", "sandwichfarm/hyprflow"]);
  applyConfig(
    env,
    options,
    (args, input) => {
      calls.push({ args, input });
      return "";
    },
    (s) => logs.push(s),
  );
  assert.equal(calls.length, 8);
  for (const call of calls.slice(2))
    assert.ok(call.args.includes("--env") && call.args.includes("production"));
  assert.equal(
    calls.find((c) => c.args.includes("BUNNY_API_KEY")).input,
    "purge-secret",
  );
  assert.ok(!JSON.stringify(logs).includes("purge-secret"));
  assert.ok(
    !JSON.stringify(calls.map((c) => c.args)).includes("storage-secret"),
  );
  applyConfig(
    env,
    { ...options, dryRun: true },
    () => assert.fail("gh write"),
    () => {},
  );
  assert.throws(() => parseArgs(["--repo"]), /Missing/);
  assert.throws(() => parseArgs(["--environment", "../oops"]), /Invalid/);
});

test("setup preserves protection rules on an existing environment", () => {
  const calls = [];
  applyConfig(
    env,
    { repo: "sandwichfarm/hyprflow", environment: "production" },
    (args) => {
      calls.push(args);
      return "production";
    },
    () => {},
  );
  assert.ok(!calls.some((args) => args.includes("PUT")));
});
