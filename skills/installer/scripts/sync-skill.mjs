#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const src = path.resolve(__dirname, "..", "..", "open-source-repo");
const dest = path.resolve(__dirname, "..", "skill");

if (!fs.existsSync(path.join(src, "SKILL.md"))) {
  console.error(`Missing skill at ${src}`);
  process.exit(1);
}

fs.rmSync(dest, { recursive: true, force: true });
fs.cpSync(src, dest, { recursive: true });
console.log(`synced ${src} -> ${dest}`);
