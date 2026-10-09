import { test } from "node:test";
import assert from "node:assert/strict";
import {
  discoverStorageHost,
  resolveSetupConfig,
  setupInputs,
} from "./bunny-storage.mjs";
const env = {
  BUNNY_STORAGE_ZONE: "example",
  BUNNY_PULL_ZONE_ID: "123",
  BUNNY_PUBLIC_URL: "https://example.b-cdn.net",
  BUNNY_STORAGE_PASSWORD: "storage-secret",
  BUNNY_API_KEY: "account-secret",
};
const response = (data) => new Response(JSON.stringify(data));

test("lookup accepts plain list responses as well as paginated responses", async () => {
  for (const data of [
    [null, { Name: "example-other", Region: "LA" }, { Name: "example", Region: "DE" }],
    { Items: [null, { Name: "example", Region: "DE" }], HasMoreItems: false },
  ]) {
    assert.equal(await discoverStorageHost("example", "key", async () => response(data)),
      "storage.bunnycdn.com");
  }
  await assert.rejects(discoverStorageHost("example", "key", async () => response([])),
    /Storage zone not found/);
});

test("full plain-list pages continue until the exact zone is found", async () => {
  const pages = [];
  assert.equal(await discoverStorageHost("example", "key", async (url) => {
    const page = new URL(url).searchParams.get("page");
    pages.push(page);
    return response(page === "0"
      ? Array.from({ length: 1000 }, () => ({ Name: "another-zone", Region: "DE" }))
      : [{ Name: "example", Region: "NY" }]);
  }), "ny.storage.bunnycdn.com");
  assert.deepEqual(pages, ["0", "1"]);
});

test("replicated zones use their primary write region, not a replica or delivery hostname", async () => {
  for (const [Region, host] of [
    ["DE", "storage.bunnycdn.com"],
    ["", "storage.bunnycdn.com"],
    ["ny", "ny.storage.bunnycdn.com"],
    ["SYD", "syd.storage.bunnycdn.com"],
  ]) {
    const actual = await discoverStorageHost(
      "example",
      "account-secret",
      async (url, options) => {
        assert.equal(new URL(url).origin, "https://api.bunny.net");
        assert.equal(new URL(url).searchParams.get("search"), "example");
        assert.equal(options.method, "GET");
        assert.equal(options.headers.AccessKey, "account-secret");
        assert.equal(options.redirect, "error");
        return response({
          Items: [
            { Name: "example", Region, ReplicationRegions: ["SG", "LA", "DE"] },
          ],
          HasMoreItems: false,
        });
      },
    );
    assert.equal(actual, host);
  }
});

test("lookup follows pagination and matches the exact storage zone name", async () => {
  const host = await discoverStorageHost("example", "key", async (url) => {
    const page = new URL(url).searchParams.get("page");
    return response(
      page === "0"
        ? {
            Items: [{ Name: "example-other", Region: "DE" }],
            HasMoreItems: true,
          }
        : { Items: [{ Name: "example", Region: "LA" }], HasMoreItems: false },
    );
  });
  assert.equal(host, "la.storage.bunnycdn.com");
});

test("old b-cdn.net host input is preserved as delivery URL and triggers endpoint discovery", async () => {
  for (const input of ["example.b-cdn.net", "https://example.b-cdn.net/"]) {
    const inputEnv = {
      ...env,
      BUNNY_PUBLIC_URL: "",
      BUNNY_STORAGE_HOST: input,
    };
    const config = await resolveSetupConfig(inputEnv, {
      log: () => {},
      discover: async (name, key) => {
        assert.equal(name, "example");
        assert.equal(key, "account-secret");
        return "ny.storage.bunnycdn.com";
      },
    });
    assert.equal(config.BUNNY_PUBLIC_URL, "https://example.b-cdn.net");
    assert.equal(config.BUNNY_STORAGE_HOST, "ny.storage.bunnycdn.com");
  }
  assert.equal(
    setupInputs({ ...env, BUNNY_STORAGE_HOST: "other.b-cdn.net" })
      .BUNNY_PUBLIC_URL,
    env.BUNNY_PUBLIC_URL,
  );
});

test("explicit upload endpoint bypasses discovery; invalid inputs fail before networking", async () => {
  const discover = () => assert.fail("unexpected lookup");
  assert.equal(
    (
      await resolveSetupConfig(
        { ...env, BUNNY_STORAGE_HOST: "storage.bunnycdn.com" },
        { discover },
      )
    ).BUNNY_STORAGE_HOST,
    "storage.bunnycdn.com",
  );
  await assert.rejects(
    resolveSetupConfig({ ...env, BUNNY_STORAGE_ZONE: "../bad" }, { discover }),
    /Invalid/,
  );
  await assert.rejects(
    resolveSetupConfig({ ...env, BUNNY_API_KEY: "" }, { discover }),
    /Missing/,
  );
});

test("lookup failures are actionable and never expose API bodies or credentials", async () => {
  await assert.rejects(
    discoverStorageHost(
      "example",
      "key",
      async () => new Response("secret-body", { status: 401 }),
    ),
    /HTTP 401.*account API key/,
  );
  await assert.rejects(
    discoverStorageHost("example", "key", async () => {
      throw new Error("secret-body");
    }),
    /network error/,
  );
  await assert.rejects(
    discoverStorageHost("example", "key", async () =>
      response({ Items: [], HasMoreItems: false }),
    ),
    /Storage zone not found/,
  );
  await assert.rejects(
    discoverStorageHost("example", "key", async () =>
      response({ Items: [{ Name: "example" }] }),
    ),
    /unrecognized primary storage region/,
  );
  await assert.rejects(
    discoverStorageHost("example", "key", async () =>
      response({ Items: [{ Name: "example", Region: "unknown" }] }),
    ),
    /unrecognized primary storage region/,
  );
  await assert.rejects(
    discoverStorageHost("example", "key", async () =>
      response({ Password: "secret-body" }),
    ),
    /Unexpected Bunny/,
  );
});
