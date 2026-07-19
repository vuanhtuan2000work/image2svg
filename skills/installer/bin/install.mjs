#!/usr/bin/env node
/**
 * Install / uninstall the open-source-repo Agent Skill into common agent skill dirs.
 *
 * Usage:
 *   open-source-repo-skill install [--global] [--agents cursor,claude,codex,gemini,agents]
 *   open-source-repo-skill uninstall [--global] [--agents ...]
 *   open-source-repo-skill list
 *   open-source-repo-skill path
 */

import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SKILL_NAME = "open-source-repo";

const AGENTS = {
  cursor: {
    project: [".cursor", "skills", SKILL_NAME],
    global: [".cursor", "skills", SKILL_NAME],
  },
  claude: {
    project: [".claude", "skills", SKILL_NAME],
    global: [".claude", "skills", SKILL_NAME],
  },
  codex: {
    project: [".codex", "skills", SKILL_NAME],
    global: [".codex", "skills", SKILL_NAME],
  },
  gemini: {
    project: [".gemini", "skills", SKILL_NAME],
    global: [".gemini", "skills", SKILL_NAME],
  },
  agents: {
    project: [".agents", "skills", SKILL_NAME],
    global: [".agents", "skills", SKILL_NAME],
  },
};

function resolveSkillSource() {
  const candidates = [
    path.resolve(__dirname, "..", "skill"),
    path.resolve(__dirname, "..", "..", "open-source-repo"),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(path.join(candidate, "SKILL.md"))) {
      return fs.realpathSync(candidate);
    }
  }
  throw new Error(
    "Could not find open-source-repo/SKILL.md next to the installer. Reinstall the package or run from the image2svg repo.",
  );
}

function parseArgs(argv) {
  const args = {
    command: "help",
    global: false,
    agents: Object.keys(AGENTS),
    cwd: process.cwd(),
  };
  const positional = [];
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === "--global" || token === "-g") {
      args.global = true;
    } else if (token === "--agents" || token === "-a") {
      const value = argv[i + 1];
      if (!value) throw new Error("--agents requires a comma-separated list");
      args.agents = value.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
      i += 1;
    } else if (token === "--cwd") {
      args.cwd = path.resolve(argv[i + 1] || "");
      i += 1;
    } else if (token === "--help" || token === "-h") {
      args.command = "help";
      return args;
    } else if (token.startsWith("-")) {
      throw new Error(`Unknown flag: ${token}`);
    } else {
      positional.push(token);
    }
  }
  if (positional[0]) args.command = positional[0];
  return args;
}

function homeDir() {
  return process.env.HOME || process.env.USERPROFILE || os.homedir();
}

function targetDir(agentKey, { global: isGlobal, cwd }) {
  const spec = AGENTS[agentKey];
  if (!spec) {
    throw new Error(`Unknown agent "${agentKey}". Valid: ${Object.keys(AGENTS).join(", ")}`);
  }
  const parts = isGlobal ? spec.global : spec.project;
  const root = isGlobal ? homeDir() : cwd;
  return path.join(root, ...parts);
}

function assertDestContained(dest, { global: isGlobal, cwd }) {
  const root = path.resolve(isGlobal ? homeDir() : cwd);
  const resolved = path.resolve(dest);
  const rel = path.relative(root, resolved);
  if (rel.startsWith("..") || path.isAbsolute(rel)) {
    throw new Error(`Refusing to write outside install root: ${resolved} (root=${root})`);
  }
}

function copyDir(src, dest) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.rmSync(dest, { recursive: true, force: true });
  fs.cpSync(src, dest, { recursive: true });
}

function skillDigest(src) {
  const bytes = fs.readFileSync(path.join(src, "SKILL.md"));
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function printHelp() {
  console.log(`open-source-repo-skill — install Agent Skill for OSS refactor workflows

Commands:
  install       Copy skill into agent skill directories
  uninstall     Remove installed skill copies
  list          Show install targets and whether skill is present
  path          Print the source skill directory

Options:
  --global, -g              Install into user home (affects ALL projects — high trust)
  --agents, -a <list>       comma list: cursor,claude,codex,gemini,agents
  --cwd <dir>               Project root (default: process.cwd())

Safer examples (prefer these):
  python skills/installer/install.py install
  npx --yes ./skills/installer install
  npx open-source-repo-skill@1.0.0 install
`);
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.command === "help") {
    printHelp();
    return;
  }

  const source = resolveSkillSource();

  if (args.command === "path") {
    console.log(source);
    return;
  }

  if (args.command === "list") {
    for (const agent of args.agents) {
      const dest = targetDir(agent, args);
      const ok = fs.existsSync(path.join(dest, "SKILL.md"));
      console.log(`${ok ? "[x]" : "[ ]"} ${agent.padEnd(8)} ${dest}`);
    }
    console.log(`source: ${source}`);
    console.log(`sha256: ${skillDigest(source)}`);
    return;
  }

  if (args.command === "install") {
    if (args.global) {
      console.error(
        "[warn] --global installs into your home skill dirs and affects ALL projects. Prefer project-local install unless you trust this skill source.",
      );
    }
    const digest = skillDigest(source);
    for (const agent of args.agents) {
      const dest = targetDir(agent, args);
      assertDestContained(dest, args);
      copyDir(source, dest);
      console.log(`installed -> ${dest}`);
    }
    console.log(`skill sha256: ${digest}`);
    console.log("\nDone. In your agent, run /open-source-repo or ask: open-source this repo");
    return;
  }

  if (args.command === "uninstall") {
    for (const agent of args.agents) {
      const dest = targetDir(agent, args);
      assertDestContained(dest, args);
      if (fs.existsSync(dest)) {
        fs.rmSync(dest, { recursive: true, force: true });
        console.log(`removed -> ${dest}`);
      } else {
        console.log(`missing  -> ${dest}`);
      }
    }
    return;
  }

  throw new Error(`Unknown command: ${args.command}`);
}

try {
  main();
} catch (err) {
  console.error(`Error: ${err instanceof Error ? err.message : String(err)}`);
  process.exitCode = 1;
}
