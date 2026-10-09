import { spawnSync } from "node:child_process";
import { createInterface } from "node:readline/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import { Writable } from "node:stream";
import { setupInputs, resolveSetupConfig } from "./bunny-storage.mjs";
import { configFromEnv, variableNames, secretNames } from "./config.mjs";
import { savedInputs, setupCheckpoint } from "./setup-checkpoint.mjs";

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
export function gh(args, input, execute = spawnSync) {
  const result = execute("gh", args, {
    input,
    encoding: "utf8",
    stdio: ["pipe", "pipe", "pipe"],
    timeout: 30_000,
    killSignal: "SIGKILL",
    env: { ...process.env, GH_PROMPT_DISABLED: "1" },
  });
  if (result.error?.code === "ETIMEDOUT")
    throw new Error(
      `GitHub CLI timed out after 30 seconds (${args[0]} ${args[1]}). Check your connection and gh auth status, then retry.`,
    );
  if (result.error?.code === "ENOENT")
    throw new Error(
      "GitHub CLI is not installed. Install it from https://cli.github.com/ and run gh auth login.",
    );
  if (result.status !== 0)
    throw new Error(
      `GitHub CLI failed (${args[0]} ${args[1]}). Check gh auth status and repository permissions.`,
    );
  return result.stdout.trim();
}

export const setupFields = [
  {
    name: "BUNNY_STORAGE_ZONE",
    label: "Storage zone name",
    purpose: "The Storage Zone where this script uploads the website files.",
    where:
      "Bunny dashboard → Storage → select your zone → copy its name (also shown as Username under Access / FTP & API Access).",
    example: "hyprflow-site (the name, not the numeric ID)",
  },
  {
    name: "BUNNY_STORAGE_HOST",
    label: "Upload endpoint (automatic)",
    purpose:
      "Setup looks up the write endpoint from your Storage Zone name and account API key. You do not need to choose a regional hostname. Replication remains managed by Bunny.",
    where:
      "Read automatically from Bunny's Storage Zone API. Your *.b-cdn.net delivery hostname belongs under Public website address below. An explicit BUNNY_STORAGE_HOST upload endpoint can still be supplied through the environment.",
    automatic: true,
  },
  {
    name: "BUNNY_PULL_ZONE_ID",
    label: "Pull Zone ID",
    purpose:
      "The numeric CDN zone ID used to clear cached pages after an upload.",
    where:
      "Bunny dashboard → CDN → select the Pull Zone connected to your storage. Copy the number after /pullzone/ in the dashboard URL (not the Storage Zone ID).",
    example: "123456 from https://dash.bunny.net/cdn/pullzone/123456/...",
  },
  {
    name: "BUNNY_PUBLIC_URL",
    label: "Public website address",
    purpose:
      "The address visitors will open. BUNNY_PUBLIC_URL is this project's variable name, not a Bunny dashboard field. It only sets the website link shown on the GitHub deployment; it does not configure DNS or choose the upload destination.",
    where:
      "Bunny dashboard → CDN → your Pull Zone → General → Hostnames. Use its default *.b-cdn.net hostname or a custom domain you have connected with HTTPS enabled.",
    example:
      "https://hyprflow-site.b-cdn.net or https://hyprflow.com — no /docs or other path. A bare hostname is accepted; https:// is added.",
  },
  {
    name: "BUNNY_STORAGE_PASSWORD",
    label: "Storage write password",
    purpose:
      "Authorizes uploads to your Storage Zone. This is not your Bunny login password or account API key.",
    where:
      "Bunny dashboard → Storage → your zone → Access / FTP & API Access → Password. Use the writable password, not the read-only password.",
    secret: true,
  },
  {
    name: "BUNNY_API_KEY",
    label: "Bunny account API key",
    purpose:
      "Reads your Storage Zone settings to detect the upload endpoint and authorizes clearing the Pull Zone cache after deployment. This is separate from the Storage Zone password.",
    where:
      "Bunny dashboard → Account → API Key: https://dash.bunny.net/account/api-key. Copy the account API key.",
    secret: true,
  },
];

function explainField(field, output) {
  output.write(
    `\n${field.label} (${field.name})\n${field.purpose}\nWhere to find it: ${field.where}\n`,
  );
  if (field.example) output.write(`Example: ${field.example}\n`);
}

export async function promptConfig(
  env,
  { input = process.stdin, output = process.stdout, discover, onChange = () => {} } = {},
) {
  const values = setupInputs(env);
  let muted = false;
  // Intercept readline's actual output rather than overriding its private methods.
  const promptOutput = new Writable({
    write(chunk, encoding, callback) {
      if (!muted) output.write(chunk, encoding);
      callback();
    },
  });
  promptOutput.isTTY = Boolean(output.isTTY);
  promptOutput.columns = output.columns || 80;
  const rl = createInterface({
    input,
    output: promptOutput,
    terminal: Boolean(input.isTTY),
    historySize: 0,
  });
  const controller = new AbortController();
  const cancel = () => controller.abort();
  rl.on("SIGINT", cancel);
  rl.on("close", cancel);
  try {
    for (const field of setupFields) {
      if (values[field.name]?.trim()) {
        try {
          configFromEnv({ [field.name]: values[field.name] }, { dryRun: true });
          output.write(
            `Using ${field.label} from ${field.name}${field.secret ? " (hidden)" : ""}.\n`,
          );
          continue;
        } catch {
          if (field.automatic) {
            delete values[field.name];
            output.write(
              `${field.name} is not an upload endpoint; setup will detect it automatically.\n`,
            );
          } else
            output.write(
              `${field.name} from the environment is invalid; enter a replacement below.\n`,
            );
        }
      }
      explainField(field, output);
      if (field.automatic) continue;
      if (field.secret)
        output.write(
          "Input is hidden: paste the value, then press Enter. Ctrl+C cancels.\n",
        );
      while (true) {
        const label = `${field.label}${field.defaultValue ? ` [${field.defaultValue}]` : ""}: `;
        let value;
        try {
          // Draw the full prompt before muting typed characters, including redraws.
          const answer = rl.question(label, { signal: controller.signal });
          muted = Boolean(field.secret);
          value = (await answer).trim() || field.defaultValue || "";
        } finally {
          muted = false;
          if (field.secret) output.write("\n");
        }
        if (!value) {
          output.write(`${field.label} is required.\n`);
          continue;
        }
        if (field.name === "BUNNY_PUBLIC_URL" && !value.includes("://"))
          value = `https://${value}`;
        try {
          values[field.name] = configFromEnv(
            { [field.name]: value },
            { dryRun: true },
          )[field.name];
        } catch (error) {
          output.write(`Invalid value: ${error.message} Try again.\n`);
          continue;
        }
        onChange(values);
        output.write(
          field.secret
            ? "Received (hidden).\n"
            : `Accepted: ${values[field.name]}\n`,
        );
        break;
      }
    }
    // Release the terminal before the network lookup; Ctrl+C can interrupt it normally.
    rl.close();
    return resolveSetupConfig(values, {
      discover,
      log: (message) => output.write(`${message}\n`),
    });
  } catch (error) {
    if (controller.signal.aborted)
      throw new Error("Setup cancelled. No GitHub settings were changed.");
    throw error;
  } finally {
    muted = false;
    rl.close();
  }
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
    log(
      "Checking GitHub environment (each request has a 30-second timeout)...",
    );
    const existing = run([
      "api",
      `repos/${repo}/environments`,
      "--paginate",
      "--jq",
      ".environments[].name",
    ]);
    if (!existing.split("\n").includes(options.environment)) {
      log(`Creating GitHub environment ${options.environment}...`);
      run([
        "api",
        "--method",
        "PUT",
        `repos/${repo}/environments/${options.environment}`,
      ]);
    }
  }
  for (const name of variableNames) {
    log(
      `${options.dryRun ? "Would save" : "Saving"} variable ${name}=${config[name] || "(not configured)"}`,
    );
    if (!options.dryRun)
      run(
        ["variable", "set", name, "--repo", repo, "--env", options.environment],
        config[name],
      );
  }
  for (const name of secretNames) {
    log(
      `${options.dryRun ? "Would save" : "Saving"} secret ${name}: ${config[name] ? "provided (hidden)" : "required before deployment"}`,
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
      : "GitHub environment configured. To deploy, run the Deploy website to Bunny workflow on main in GitHub Actions.",
  );
}
export async function runSetup(options, {
  env = process.env,
  input = process.stdin,
  output = process.stdout,
  run = gh,
  discover,
  checkpointDirectory = fileURLToPath(new URL("../../.bunny-setup/", import.meta.url)),
} = {}) {
  const log = (message) => output.write(`${message}\n`);
  if (options.dryRun) {
    const values = setupInputs(env);
    const config = configFromEnv(values, { dryRun: true });
    if (!values.BUNNY_STORAGE_HOST?.trim())
      config.BUNNY_STORAGE_HOST = "(detected automatically during setup)";
    applyConfig(config, options, run, log);
    return;
  }
  log("Checking GitHub CLI authentication (30-second timeout)...");
  run(["auth", "status", "--hostname", "github.com"]);
  const repo = options.repo || run(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]);
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) throw new Error("Repository must be OWNER/REPO.");
  const target = { ...options, repo };
  const checkpoint = input.isTTY ? setupCheckpoint(checkpointDirectory, target) : undefined;
  let values = setupInputs(env);
  if (checkpoint) {
    const saved = checkpoint.load();
    const exported = savedInputs(env);
    values = setupInputs({ ...saved, ...exported });
    // A saved endpoint belongs to the previous zone/account, unless explicitly overridden.
    if (!exported.BUNNY_STORAGE_HOST && ["BUNNY_STORAGE_ZONE", "BUNNY_API_KEY"].some(
      (name) => exported[name] && exported[name] !== saved[name],
    )) delete values.BUNNY_STORAGE_HOST;
    if (Object.keys(saved).length) log("Resuming saved answers. Exported values override saved answers; secrets remain hidden.");
    checkpoint.save(values);
    log(`Answers, including secrets, are saved locally in ${checkpoint.path} (owner-only access, Git-ignored). Rerun the same command to resume. The file is removed after success.`);
  }
  log("Configure an existing Bunny Storage + Pull Zone. GitHub settings are unchanged until all values are valid.");
  try {
    const config = input.isTTY
      ? await promptConfig(values, { input, output, discover, onChange: (answers) => checkpoint.save(answers) })
      : await resolveSetupConfig(values, { discover, log });
    checkpoint?.save(config);
    applyConfig(config, target, run, log);
    checkpoint?.clear();
    if (checkpoint) log("Local resume file removed.");
  } catch (error) {
    if (checkpoint) log(`Saved answers kept in ${checkpoint.path}. Rerun the same setup command to resume without re-entering them.`);
    throw error;
  }
}

async function main() {
  if (process.argv.slice(2).includes("--help")) {
    console.log(
      "Usage: npm run setup:bunny -- [--repo OWNER/REPO] [--environment production] [--dry-run]\n\nSets GitHub variables and secrets for an existing Bunny Storage + Pull Zone.\nInteractive setup explains and validates each value. Secrets stay hidden. The upload endpoint is detected automatically using a read-only Bunny API request.\nInteractive answers (including secrets) are saved in .bunny-setup/ with owner-only permissions and removed after success. Rerun the same command to resume; exported values override saved answers. Delete .bunny-setup/ to discard saved answers.\n--dry-run shows planned settings without prompts, resume files, or GitHub writes.",
    );
    for (const field of setupFields) explainField(field, process.stdout);
    return;
  }
  await runSetup(parseArgs(process.argv.slice(2)));
}
if (import.meta.url === pathToFileURL(process.argv[1] || "").href)
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
