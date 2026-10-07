import { readFile, stat } from "node:fs/promises";
import { resolve, join } from "node:path";
import { collectFiles } from "./deploy-bunny.mjs";
const root = resolve("dist");
const files = await collectFiles(root);
const failures = [];
for (const file of files.filter((file) => file.endsWith(".html"))) {
  const html = await readFile(join(root, file), "utf8");
  for (const [, attribute] of html.matchAll(
    /(?:href|src|poster)="([^"#]+)"/g,
  )) {
    const href = attribute.replaceAll("&amp;", "&");
    const url = new URL(href, `https://build.invalid/${file}`);
    if (url.origin !== "https://build.invalid") continue;
    const pathname = decodeURIComponent(url.pathname);
    const target = join(
      root,
      pathname.endsWith("/") ? pathname + "index.html" : pathname,
    );
    try {
      if (!(await stat(target)).isFile())
        failures.push(`${file} → ${pathname}`);
    } catch {
      failures.push(`${file} → ${pathname}`);
    }
  }
}
const docs = await readFile(join(root, "docs/index.html"), "utf8");
if (!docs.includes("/docs/assets/"))
  failures.push("Docs assets must use the /docs/ prefix.");
if (failures.length)
  throw new Error(`Broken build links:\n${[...new Set(failures)].join("\n")}`);
console.log(
  `Verified ${files.length} output files and local HTML links; docs are under /docs/.`,
);
