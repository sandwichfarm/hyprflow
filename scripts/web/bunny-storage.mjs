import { configFromEnv } from "./config.mjs";

// Bunny HTTP Storage uses Region for writes; ReplicationRegions are delivery replicas.
const endpoints = {
  "": "storage.bunnycdn.com",
  DE: "storage.bunnycdn.com",
  UK: "uk.storage.bunnycdn.com",
  NY: "ny.storage.bunnycdn.com",
  LA: "la.storage.bunnycdn.com",
  SG: "sg.storage.bunnycdn.com",
  SE: "se.storage.bunnycdn.com",
  BR: "br.storage.bunnycdn.com",
  JH: "jh.storage.bunnycdn.com",
  SYD: "syd.storage.bunnycdn.com",
};

export function setupInputs(env) {
  const values = { ...env };
  // Accommodate a delivery hostname entered under the old, ambiguous variable name.
  try {
    const input = values.BUNNY_STORAGE_HOST?.trim();
    const url = new URL(input?.includes("://") ? input : `https://${input}`);
    if (
      url.protocol === "https:" &&
      /^[a-z0-9-]+\.b-cdn\.net$/.test(url.hostname) &&
      !url.username &&
      !url.password &&
      !url.port &&
      url.pathname === "/" &&
      !url.search &&
      !url.hash
    ) {
      values.BUNNY_PUBLIC_URL ||= url.origin;
      delete values.BUNNY_STORAGE_HOST;
    }
  } catch {
    /* Normal validation will explain any invalid explicit endpoint. */
  }
  return values;
}

export async function discoverStorageHost(zoneName, apiKey, fetchImpl = fetch) {
  const signal = AbortSignal.timeout(30_000);
  for (let page = 0; page < 100; page++) {
    const params = new URLSearchParams({
      page: String(page),
      perPage: "1000",
      search: zoneName,
    });
    let response, data;
    try {
      response = await fetchImpl(
        `https://api.bunny.net/storagezone?${params}`,
        {
          method: "GET",
          headers: { AccessKey: apiKey, Accept: "application/json" },
          redirect: "error",
          signal,
        },
      );
      if (response.ok) data = await response.json();
    } catch {
      throw new Error(
        "Could not look up the Bunny upload endpoint (network error, invalid response, or 30-second timeout). No GitHub settings changed; retry setup.",
      );
    }
    if (!response.ok)
      throw new Error(
        `Bunny storage lookup failed: HTTP ${response.status}. Check the account API key and its Storage permissions. No GitHub settings changed.`,
      );
    if (!Array.isArray(data?.Items))
      throw new Error(
        "Unexpected Bunny storage lookup response. No GitHub settings changed.",
      );
    const zone = data.Items.find((item) => item.Name === zoneName);
    if (zone) {
      const host =
        typeof zone.Region === "string"
          ? endpoints[zone.Region.toUpperCase()]
          : undefined;
      if (!host)
        throw new Error(
          "Bunny returned an unrecognized primary storage region. Set BUNNY_STORAGE_HOST to the HTTP upload hostname from Storage → Access, then rerun setup. No GitHub settings changed.",
        );
      return host;
    }
    if (!data.HasMoreItems)
      throw new Error(
        "Storage zone not found in this Bunny account. Check BUNNY_STORAGE_ZONE against Storage → zone name, and use that account's API key. No GitHub settings changed.",
      );
  }
  throw new Error(
    "Bunny storage lookup exceeded its page limit. No GitHub settings changed.",
  );
}

export async function resolveSetupConfig(
  env,
  { discover = discoverStorageHost, log = console.log } = {},
) {
  const values = setupInputs(env);
  // Validate the other inputs before making a request. The temporary host is never saved.
  const config = configFromEnv({
    ...values,
    BUNNY_STORAGE_HOST: values.BUNNY_STORAGE_HOST || "storage.bunnycdn.com",
  });
  if (!values.BUNNY_STORAGE_HOST?.trim()) {
    log(
      "Looking up the upload endpoint from Bunny (30-second timeout); replication settings are unchanged...",
    );
    config.BUNNY_STORAGE_HOST = await discover(
      config.BUNNY_STORAGE_ZONE,
      config.BUNNY_API_KEY,
    );
    log(`Detected upload endpoint: ${config.BUNNY_STORAGE_HOST}`);
  }
  return configFromEnv(config);
}
