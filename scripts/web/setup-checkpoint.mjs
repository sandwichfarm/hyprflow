import {
  constants, closeSync, fstatSync, lstatSync, mkdirSync, openSync,
  readFileSync, renameSync, unlinkSync, writeFileSync,
} from "node:fs";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
import { variableNames, secretNames } from "./config.mjs";

const names = [...variableNames, ...secretNames];
export function savedInputs(values) {
  return Object.fromEntries(names
    .filter((name) => typeof values[name] === "string" && values[name].trim())
    .map((name) => [name, values[name].trim()]));
}

// Private, per-repository/environment resume data. Never store unrelated env vars.
export function setupCheckpoint(directory, { repo, environment }) {
  const path = join(directory, `${encodeURIComponent(`${repo}/${environment}`)}.json`);
  function checkPrivate(stat) {
    if ((stat.mode & 0o077) || (process.getuid && stat.uid !== process.getuid()))
      throw new Error("Setup resume data must be owned by you and accessible only to you.");
  }
  function prepare() {
    mkdirSync(directory, { recursive: true, mode: 0o700 });
    const stat = lstatSync(directory);
    if (!stat.isDirectory()) throw new Error("Setup resume directory must not be a symlink.");
    checkPrivate(stat);
  }
  return {
    path,
    load() {
      prepare();
      let fd;
      try {
        fd = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
        const stat = fstatSync(fd);
        if (!stat.isFile()) throw new Error("Invalid setup resume file.");
        checkPrivate(stat);
        let data;
        try { data = JSON.parse(readFileSync(fd, "utf8")); }
        catch { throw new Error("Cannot read setup resume data. The saved file has been kept."); }
        if (data?.repo !== repo || data?.environment !== environment || !data?.values)
          throw new Error("Setup resume data does not match this repository and environment.");
        return savedInputs(data.values);
      } catch (error) {
        if (error.code === "ENOENT") return {};
        throw error;
      } finally {
        if (fd !== undefined) closeSync(fd);
      }
    },
    save(values) {
      prepare();
      const temporary = `${path}.${randomUUID()}.tmp`;
      try {
        writeFileSync(temporary, JSON.stringify({ repo, environment, values: savedInputs(values) }),
          { flag: "wx", mode: 0o600 });
        renameSync(temporary, path);
      } finally {
        try { unlinkSync(temporary); } catch (error) { if (error.code !== "ENOENT") throw error; }
      }
    },
    clear() {
      try { unlinkSync(path); } catch (error) { if (error.code !== "ENOENT") throw error; }
    },
  };
}
