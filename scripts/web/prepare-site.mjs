import { mkdir, copyFile } from "node:fs/promises";
await mkdir("website/public/media", { recursive: true });
await copyFile(
  "artifacts/appearance/02-solid.png",
  "website/public/media/poster.png",
);
await copyFile(
  "artifacts/appearance/configurations.mp4",
  "website/public/media/navigation.mp4",
);
