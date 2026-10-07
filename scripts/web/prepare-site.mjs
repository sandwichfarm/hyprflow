import { mkdir, copyFile } from "node:fs/promises";
await mkdir("website/public/media", { recursive: true });
await copyFile(
  "artifacts/final/navigation/02-open.png",
  "website/public/media/poster.png",
);
await copyFile(
  "artifacts/final/navigation/navigation.mp4",
  "website/public/media/navigation.mp4",
);
