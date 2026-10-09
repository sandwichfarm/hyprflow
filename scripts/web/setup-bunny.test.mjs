import { test } from "node:test";
import assert from "node:assert/strict";
import { PassThrough, Writable } from "node:stream";
import { promptConfig, setupFields, gh, runSetup } from "./setup-bunny.mjs";
import { configFromEnv } from "./config.mjs";
import { setupCheckpoint } from "./setup-checkpoint.mjs";
import { mkdtempSync, rmSync, statSync, existsSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

function terminal() {
  const input = new PassThrough();
  input.isTTY = true;
  input.setRawMode = () => {};
  let transcript = "";
  const output = new Writable({
    write(chunk, encoding, done) {
      transcript += chunk.toString();
      done();
    },
  });
  output.isTTY = true;
  output.columns = 120;
  return {
    input,
    output,
    get transcript() {
      return transcript;
    },
  };
}
async function waitFor(term, text) {
  const deadline = Date.now() + 2000;
  while (!term.transcript.includes(text)) {
    assert.ok(Date.now() < deadline, `Missing prompt: ${text}`);
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

test("interactive setup explains each field, validates immediately, and hides secret keystrokes", async () => {
  const term = terminal();
  const result = promptConfig(
    {},
    { ...term, discover: async () => "ny.storage.bunnycdn.com" },
  );
  for (const [prompt, value] of [
    ["Storage zone name: ", "example-site"],
    ["Pull Zone ID: ", "not-an-id"],
    ["Try again.", "12345"],
    ["Public website address: ", "https://example-site.b-cdn.net/docs"],
    ["without /docs", "example-site.b-cdn.net"],
    ["Storage write password: ", "private-storage-value"],
    ["Bunny account API key: ", "private-api-value"],
  ]) {
    await waitFor(term, prompt);
    term.input.write(value + "\n");
  }
  const config = await result;
  assert.equal(config.BUNNY_PULL_ZONE_ID, "12345");
  assert.equal(config.BUNNY_PUBLIC_URL, "https://example-site.b-cdn.net");
  assert.equal(config.BUNNY_STORAGE_HOST, "ny.storage.bunnycdn.com");
  assert.equal(config.BUNNY_STORAGE_PASSWORD, "private-storage-value");
  assert.equal(config.BUNNY_API_KEY, "private-api-value");
  assert.ok(!term.transcript.includes("private-storage-value"));
  assert.ok(!term.transcript.includes("private-api-value"));
  for (const field of setupFields) {
    assert.ok(term.transcript.includes(field.purpose));
    assert.ok(term.transcript.includes(field.where));
  }
  // readline's initial erase/redraw must include the secret prompt, not erase it.
  assert.match(term.transcript, /\x1b\[0JStorage write password: /);
  assert.match(term.transcript, /\x1b\[0JBunny account API key: /);
  assert.match(term.transcript, /Input is hidden/);
  assert.match(term.transcript, /Received \(hidden\)/);
  assert.ok(!term.transcript.includes("Storage API hostname ["));
  assert.match(
    term.transcript,
    /Detected upload endpoint: ny.storage.bunnycdn.com/,
  );
});

test("an invalid exported value can be corrected without re-entering valid settings", async () => {
  const term = terminal();
  const result = promptConfig(
    {
      BUNNY_STORAGE_ZONE: "example-site",
      BUNNY_STORAGE_HOST: "storage.bunnycdn.com",
      BUNNY_PULL_ZONE_ID: "123",
      BUNNY_PUBLIC_URL: "a bad URL",
      BUNNY_STORAGE_PASSWORD: "existing-storage-secret",
      BUNNY_API_KEY: "existing-account-secret",
    },
    term,
  );
  await waitFor(term, "Public website address: ");
  term.input.write("https://example-site.b-cdn.net\n");
  assert.equal(
    (await result).BUNNY_PUBLIC_URL,
    "https://example-site.b-cdn.net",
  );
  assert.match(term.transcript, /from the environment is invalid/);
  assert.ok(!term.transcript.includes("existing-storage-secret"));
  assert.ok(!term.transcript.includes("existing-account-secret"));
});

for (const [name, end] of [
  ["Ctrl+C", (term) => term.input.write("\x03")],
  ["EOF", (term) => term.input.end()],
]) {
  test(`${name} exits a pending prompt instead of waiting forever`, async () => {
    const term = terminal();
    const result = promptConfig(
      {},
      { ...term, discover: async () => "ny.storage.bunnycdn.com" },
    );
    const rejection = assert.rejects(
      result,
      /Setup cancelled. No GitHub settings were changed/,
    );
    await waitFor(term, "Storage zone name: ");
    end(term);
    await rejection;
  });
}

test("GitHub commands are noninteractive, time out, and never include secrets in diagnostics", () => {
  assert.throws(
    () =>
      gh(
        ["secret", "set", "BUNNY_API_KEY"],
        "private-value",
        (_command, _args, options) => {
          assert.equal(options.timeout, 30_000);
          assert.equal(options.killSignal, "SIGKILL");
          assert.equal(options.env.GH_PROMPT_DISABLED, "1");
          assert.equal(options.input, "private-value");
          return {
            status: null,
            error: { code: "ETIMEDOUT" },
            stderr: "private-value",
          };
        },
      ),
    /timed out after 30 seconds/,
  );
  assert.throws(
    () =>
      gh(["auth", "status"], undefined, () => ({
        status: null,
        error: { code: "ENOENT" },
      })),
    /not installed/,
  );
  assert.throws(
    () =>
      gh(["secret", "set"], "private-value", () => ({
        status: 1,
        stderr: "private-value",
      })),
    (error) => !error.message.includes("private-value"),
  );
});

test("public website address rejects dashboard and upload endpoints with useful errors", () => {
  for (const value of [
    "https://dash.bunny.net",
    "https://api.bunny.net",
    "https://ny.storage.bunnycdn.com",
    "https://example.com/docs",
  ]) {
    assert.throws(
      () => configFromEnv({ BUNNY_PUBLIC_URL: value }, { dryRun: true }),
      /public website HTTPS origin/,
    );
  }
  assert.throws(
    () => configFromEnv({ BUNNY_PUBLIC_URL: "not a URL" }, { dryRun: true }),
    /public website address/,
  );
});

test("cancelling hidden input exits without echoing the partial secret", async () => {
  const term = terminal();
  const result = promptConfig(
    {
      BUNNY_STORAGE_ZONE: "site",
      BUNNY_STORAGE_HOST: "storage.bunnycdn.com",
      BUNNY_PULL_ZONE_ID: "123",
      BUNNY_PUBLIC_URL: "https://site.b-cdn.net",
    },
    term,
  );
  const rejection = assert.rejects(result, /Setup cancelled/);
  await waitFor(term, "Storage write password: ");
  term.input.write("partial-secret");
  term.input.write("\x03");
  await rejection;
  assert.ok(!term.transcript.includes("partial-secret"));
});

test("answers survive lookup failure, restart, and partial GitHub save without re-entry", async (t) => {
  const directory = mkdtempSync(join(tmpdir(), "bunny-resume-test-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const options = { repo: "owner/site", environment: "production", dryRun: false };
  const checkpoint = setupCheckpoint(directory, options);
  const term = terminal();
  const noWrites = (args) => {
    assert.equal(args[0], "auth");
    return "";
  };
  const first = assert.rejects(runSetup(options, {
    ...term, env: { UNRELATED_SECRET: "do-not-save" }, checkpointDirectory: directory,
    run: noWrites,
    discover: async () => { throw new Error("Unexpected Bunny storage lookup response."); },
  }), /Unexpected Bunny/);
  for (const [prompt, value] of [
    ["Storage zone name: ", "example-site"],
    ["Pull Zone ID: ", "12345"],
    ["Public website address: ", "example-site.b-cdn.net"],
    ["Storage write password: ", "private-storage-value"],
    ["Bunny account API key: ", "private-api-value"],
  ]) {
    await waitFor(term, prompt);
    // Earlier answers are saved before the next question, even before networking.
    if (prompt === "Pull Zone ID: ") assert.equal(checkpoint.load().BUNNY_STORAGE_ZONE, "example-site");
    term.input.write(value + "\n");
  }
  await first;
  const expected = {
    BUNNY_STORAGE_ZONE: "example-site", BUNNY_PULL_ZONE_ID: "12345",
    BUNNY_PUBLIC_URL: "https://example-site.b-cdn.net",
    BUNNY_STORAGE_PASSWORD: "private-storage-value", BUNNY_API_KEY: "private-api-value",
  };
  assert.deepEqual(checkpoint.load(), expected);
  assert.equal(statSync(checkpoint.path).mode & 0o777, 0o600);
  assert.equal(statSync(directory).mode & 0o777, 0o700);
  assert.match(term.transcript, /Saved answers kept/);

  const secondTerm = terminal();
  await assert.rejects(runSetup(options, {
    ...secondTerm, env: {}, checkpointDirectory: directory,
    discover: async (name, key) => {
      assert.equal(name, expected.BUNNY_STORAGE_ZONE);
      assert.equal(key, expected.BUNNY_API_KEY);
      return "ny.storage.bunnycdn.com";
    },
    run: (args) => {
      if (args[0] === "secret") throw new Error("GitHub CLI timed out");
      return args[0] === "api" ? "production" : "";
    },
  }), /GitHub CLI timed out/);
  assert.equal(checkpoint.load().BUNNY_STORAGE_HOST, "ny.storage.bunnycdn.com");

  const thirdTerm = terminal();
  const writes = {};
  await runSetup(options, {
    ...thirdTerm, env: { BUNNY_PULL_ZONE_ID: "67890" }, checkpointDirectory: directory,
    discover: () => assert.fail("already detected endpoint should be reused"),
    run: (args, value) => {
      if (["variable", "secret"].includes(args[0])) writes[args[2]] = value;
      return args[0] === "api" ? "production" : "";
    },
  });
  assert.deepEqual(writes, { ...expected, BUNNY_STORAGE_HOST: "ny.storage.bunnycdn.com", BUNNY_PULL_ZONE_ID: "67890" });
  assert.equal(existsSync(checkpoint.path), false);
  for (const resumed of [secondTerm, thirdTerm]) {
    assert.match(resumed.transcript, /Resuming saved answers/);
    assert.doesNotMatch(resumed.transcript, /Storage write password: |Bunny account API key: /);
  }
  for (const session of [term, secondTerm, thirdTerm]) {
    assert.doesNotMatch(session.transcript, /private-storage-value|private-api-value|do-not-save/);
  }
});

test("dry runs never load or create a resume file", async (t) => {
  const directory = mkdtempSync(join(tmpdir(), "bunny-dry-test-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const checkpointDirectory = join(directory, "absent");
  await runSetup({ repo: "owner/site", environment: "production", dryRun: true }, {
    ...terminal(), env: {}, checkpointDirectory,
    run: () => assert.fail("dry run must not contact GitHub when repo is supplied"),
    discover: () => assert.fail("dry run must not contact Bunny"),
  });
  assert.equal(existsSync(checkpointDirectory), false);
});

test("changing the saved zone redetects its endpoint while keeping other answers", async (t) => {
  const directory = mkdtempSync(join(tmpdir(), "bunny-zone-test-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const options = { repo: "owner/site", environment: "production", dryRun: false };
  setupCheckpoint(directory, options).save({
    BUNNY_STORAGE_ZONE: "old-zone", BUNNY_STORAGE_HOST: "ny.storage.bunnycdn.com",
    BUNNY_PULL_ZONE_ID: "123", BUNNY_PUBLIC_URL: "https://example.b-cdn.net",
    BUNNY_STORAGE_PASSWORD: "storage-secret", BUNNY_API_KEY: "account-secret",
  });
  let detected = false;
  await runSetup(options, {
    ...terminal(), env: { BUNNY_STORAGE_ZONE: "new-zone" }, checkpointDirectory: directory,
    discover: async (zone, key) => {
      assert.equal(zone, "new-zone");
      assert.equal(key, "account-secret");
      detected = true;
      return "storage.bunnycdn.com";
    },
    run: (args, value) => {
      if (args[2] === "BUNNY_STORAGE_HOST") assert.equal(value, "storage.bunnycdn.com");
      return args[0] === "api" ? "production" : "";
    },
  });
  assert.ok(detected);
});
