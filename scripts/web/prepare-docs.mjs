import { mkdir, readdir, copyFile, cp } from "node:fs/promises";
await mkdir("docs/public/reference", { recursive: true });
for (const file of await readdir("docs/reference")) {
  if (/\.(jpg|png)$/.test(file))
    await copyFile(`docs/reference/${file}`, `docs/public/reference/${file}`);
}
await copyFile("website/public/favicon.svg", "docs/public/favicon.svg");

// Keep SDK receipts and patch downloads adjacent to the rendered preparation guide.
await cp("docs/testing/vulkan", "docs/public/testing/vulkan", {
  recursive: true,
  filter: (path) => !path.endsWith(".md"),
});
