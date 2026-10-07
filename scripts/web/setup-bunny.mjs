import { spawnSync } from "node:child_process";
import { createInterface } from "node:readline/promises";
import { pathToFileURL } from "node:url";
import { configFromEnv, variableNames, secretNames } from "./config.mjs";

export function parseArgs(args) {
  const options = { repo: "", environment: "production", dryRun: false };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--dry-run") options.dryRun = true;
    else if (args[i] === "--repo" || args[i] === "--environment") {
      const key = args[i].slice(2);
      if (!args[++i] || args[i].startsWith("--"))
        throw new Error(`Missing --${key} value.`);
      options[key] = args[i];
    } else throw new Error(`Unknown option: ${args[i]}`);
  }
  if (options.repo && !/^[\w.-]+\/[\w.-]+$/.test(options.repo))
    throw new Error("Repository must be OWNER/REPO.");
  if (!/^[\w.-]+$/.test(options.environment))
    throw new Error("Invalid environment name.");
  return options;
}
function gh(args, input) {
  const result = spawnSync("gh", args, {
    input,
    encoding: "utf8",
    stdio: ["pipe", "pipe", "pipe"],
  });
  if (result.status !== 0)
    throw new Error(
      `GitHub CLI failed (${args[0]} ${args[1]}). Check gh auth status and repository permissions.`,
    );
  return result.stdout.trim();
}
export function applyConfig(config, options, run = gh, log = console.log) {
  const repo =
    options.repo ||
    run(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]);
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo))
    throw new Error("Repository must be OWNER/REPO.");
  log(
    `${options.dryRun ? "Dry run: configure" : "Configuring"} ${repo}, environment ${options.environment}`,
  );
  if (!options.dryRun) {
    const existing = run([
      "api",
      `repos/${repo}/environments`,
      "--paginate",
      "--jq",
      ".environments[].name",
    ]);
    if (!existing.split("\n").includes(options.environment)) {
      run([
        "api",
        "--method",
        "PUT",
        `repos/${repo}/environments/${options.environment}`,
      ]);
    }
  }
  for (const name of variableNames) {
    log(`Variable ${name}=${config[name]}`);
    if (!options.dryRun)
      run(
        ["variable", "set", name, "--repo", repo, "--env", options.environment],
        config[name],
      );
  }
  for (const name of secretNames) {
    log(
      `Secret ${name}: ${config[name] ? "provided (hidden)" : "required before deployment"}`,
    );
    if (!options.dryRun)
      run(
        ["secret", "set", name, "--repo", repo, "--env", options.environment],
        config[name],
      );
  }
  log(
    options.dryRun
      ? "No GitHub settings changed."
      : "GitHub environment configured. Merge the website PR to main to deploy.",
  );
}
async function main() {
  const options = parseArgs(process.argv.slice(2));
  const env = {
    ...process.env,
    BUNNY_STORAGE_HOST:
      process.env.BUNNY_STORAGE_HOST || "storage.bunnycdn.com",
  };
  if (!options.dryRun && process.stdin.isTTY) {
    const rl = createInterface({
      input: process.stdin,
      output: process.stdout,
    });
    try {
      for (const name of [...variableNames, ...secretNames]) {
        if (env[name]) continue;
        if (secretNames.includes(name)) {
          process.stdout.write(`${name} (hidden): `);
          const original = rl._writeToOutput;
          rl._writeToOutput = () => {};
          try {
            env[name] = await rl.question("");
          } finally {
            rl._writeToOutput = original;
            process.stdout.write("\n");
          }
        } else env[name] = await rl.question(`${name}: `);
      }
    } finally {
      rl.close();
    }
  }
  const config = configFromEnv(env, { dryRun: options.dryRun });
  applyConfig(config, options);
}
if (import.meta.url === pathToFileURL(process.argv[1] || "").href)
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
