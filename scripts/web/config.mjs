export const variableNames = [
  "BUNNY_STORAGE_ZONE",
  "BUNNY_STORAGE_HOST",
  "BUNNY_PULL_ZONE_ID",
  "BUNNY_PUBLIC_URL",
];
export const secretNames = ["BUNNY_STORAGE_PASSWORD", "BUNNY_API_KEY"];
export function configFromEnv(env, { dryRun = false } = {}) {
  const config = Object.fromEntries(
    [...variableNames, ...secretNames].map((name) => [
      name,
      env[name]?.trim() || "",
    ]),
  );
  config.BUNNY_STORAGE_HOST ||= "storage.bunnycdn.com";
  if (
    !/^(?:[a-z]{2,3}\.)?storage\.bunnycdn\.com$/.test(config.BUNNY_STORAGE_HOST)
  )
    throw new Error(
      "BUNNY_STORAGE_HOST must be a Bunny regional storage hostname (no scheme or path).",
    );
  if (
    config.BUNNY_STORAGE_ZONE &&
    !/^[a-zA-Z0-9_-]+$/.test(config.BUNNY_STORAGE_ZONE)
  )
    throw new Error("Invalid BUNNY_STORAGE_ZONE.");
  if (
    config.BUNNY_PULL_ZONE_ID &&
    !/^[1-9]\d*$/.test(config.BUNNY_PULL_ZONE_ID)
  )
    throw new Error("BUNNY_PULL_ZONE_ID must be a positive integer.");
  if (config.BUNNY_PUBLIC_URL) {
    const url = new URL(config.BUNNY_PUBLIC_URL);
    if (
      url.protocol !== "https:" ||
      url.username ||
      url.password ||
      url.pathname !== "/" ||
      url.search ||
      url.hash
    )
      throw new Error(
        "BUNNY_PUBLIC_URL must be an HTTPS origin without credentials or a path.",
      );
    config.BUNNY_PUBLIC_URL = url.origin;
  }
  if (!dryRun)
    for (const [name, value] of Object.entries(config))
      if (!value)
        throw new Error(`Missing ${name}. Run npm run setup:bunny first.`);
  return config;
}
