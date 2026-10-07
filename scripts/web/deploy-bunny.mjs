import { readdir, readFile, stat } from "node:fs/promises";
import { resolve, join, relative, extname } from "node:path";
import { pathToFileURL } from "node:url";
import { createHash } from "node:crypto";
import { configFromEnv } from "./config.mjs";

const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".mp4": "video/mp4",
  ".woff2": "font/woff2",
  ".txt": "text/plain",
};

export async function collectFiles(directory) {
  const files = [];
  async function walk(path) {
    for (const entry of await readdir(path, { withFileTypes: true })) {
      if (entry.isSymbolicLink())
        throw new Error("Refusing to deploy a symbolic link.");
      if (entry.name.startsWith("."))
        throw new Error("Refusing to deploy hidden files.");
      const full = join(path, entry.name);
      if (entry.isDirectory()) await walk(full);
      else if (entry.isFile())
        files.push(relative(directory, full).split("\\").join("/"));
    }
  }
  await walk(directory);
  for (const required of [
    "index.html",
    "docs/index.html",
    "docs/getting-started.html",
  ]) {
    if (
      !files.includes(required) ||
      (await stat(join(directory, required))).size === 0
    )
      throw new Error(
        `Incomplete build: missing or empty ${required}. Run npm run build.`,
      );
  }
  // Upload dependencies first, then pages, then the two entrypoints.
  const rank = (file) =>
    ["index.html", "docs/index.html"].includes(file)
      ? 2
      : file.endsWith(".html")
        ? 1
        : 0;
  return files.sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

export async function request(
  url,
  options,
  {
    fetchImpl = fetch,
    sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
  } = {},
) {
  for (let attempt = 0; attempt < 3; attempt++) {
    let response;
    try {
      response = await fetchImpl(url, {
        ...options,
        redirect: "error",
        signal: AbortSignal.timeout(120_000),
      });
    } catch {
      if (attempt === 2)
        throw new Error(
          "Bunny request failed after 3 attempts (network or timeout).",
        );
    }
    if (response?.ok) {
      await response.arrayBuffer();
      return;
    }
    if (response) {
      await response.arrayBuffer();
      if ((response.status !== 429 && response.status < 500) || attempt === 2)
        throw new Error(`Bunny request failed: HTTP ${response.status}.`);
    }
    await sleep(1000 * 2 ** attempt);
  }
}

export async function deploy({
  directory = resolve("dist"),
  env = process.env,
  dryRun = false,
  fetchImpl = fetch,
  sleep,
  log = console.log,
} = {}) {
  const config = configFromEnv(env, { dryRun });
  const files = await collectFiles(directory);
  const zone = config.BUNNY_STORAGE_ZONE || "YOUR_STORAGE_ZONE";
  const base = `https://${config.BUNNY_STORAGE_HOST}/${zone}/`;
  for (const file of files) {
    const url = base + file.split("/").map(encodeURIComponent).join("/");
    if (dryRun) {
      log(`PUT ${url}`);
      continue;
    }
    const body = await readFile(join(directory, file));
    await request(
      url,
      {
        method: "PUT",
        headers: {
          AccessKey: config.BUNNY_STORAGE_PASSWORD,
          "Content-Type":
            mimeTypes[extname(file)] || "application/octet-stream",
          Checksum: createHash("sha256")
            .update(body)
            .digest("hex")
            .toUpperCase(),
        },
        body,
      },
      { fetchImpl, sleep },
    );
    log(`Uploaded ${file}`);
  }
  const purgeUrl = `https://api.bunny.net/pullzone/${config.BUNNY_PULL_ZONE_ID || "YOUR_PULL_ZONE_ID"}/purgeCache`;
  if (dryRun) log(`POST ${purgeUrl}`);
  else
    await request(
      purgeUrl,
      { method: "POST", headers: { AccessKey: config.BUNNY_API_KEY } },
      { fetchImpl, sleep },
    );
  log(
    `${dryRun ? "Dry run:" : "Deployed"} ${files.length} files; ${dryRun ? "no remote changes." : "CDN purge requested."}`,
  );
  return files;
}
if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  const args = process.argv.slice(2);
  if (args.some((arg) => arg !== "--dry-run")) {
    console.error("Usage: node scripts/web/deploy-bunny.mjs [--dry-run]");
    process.exitCode = 1;
  } else
    deploy({ dryRun: args.includes("--dry-run") }).catch((error) => {
      console.error(error.message);
      process.exitCode = 1;
    });
}
