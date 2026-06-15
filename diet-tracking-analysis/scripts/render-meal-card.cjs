#!/usr/bin/env node
/**
 * render-meal-card.cjs — Render a meal check-in card (HTML template) to a PNG.
 *
 * Carries ①菜品明细 + ②营养汇总 as an image so the text reply only needs to
 * keep ③建议/点评. Pure rendering — does NOT transform or judge the data, it
 * injects the JSON verbatim into the template.
 *
 * Usage:
 *   node render-meal-card.cjs --data '<card json>' --output /path/to/card.png
 *   echo '<card json>' | node render-meal-card.cjs --output /path/to/card.png
 *
 * On success prints the output path to stdout (for the caller to parse).
 * On failure exits non-zero and prints the error to stderr, so the caller
 * (agent) can fall back to a plain-text reply.
 *
 * Fully portable: NO absolute paths hard-coded. playwright-core and the
 * chromium binary are resolved at runtime (see resolvePlaywright / findChromium).
 */

const fs = require("fs");
const os = require("os");
const path = require("path");

/**
 * Resolve playwright-core without hard-coding any absolute install path.
 * Tries, in order:
 *   1. standard require (NODE_PATH / nearby node_modules)
 *   2. node_modules/playwright-core under a set of candidate base dirs:
 *      OPENCLAW_HOME, repo root derived from OPENCLAW_STATE_DIR, cwd, and
 *      ancestors of __dirname that contain openclaw/node_modules.
 * Returns the playwright-core module. Throws a clear error if none resolve.
 */
function resolvePlaywright() {
  // 1. Standard resolution first.
  try {
    return require("playwright-core");
  } catch (_) {
    /* fall through to candidate base dirs */
  }

  const candidates = [];
  const addBase = (base) => {
    if (!base) return;
    candidates.push(path.join(base, "node_modules", "playwright-core"));
    // Common layout in this repo: <root>/openclaw/node_modules/playwright-core
    candidates.push(path.join(base, "openclaw", "node_modules", "playwright-core"));
  };

  addBase(process.env.OPENCLAW_HOME);

  // OPENCLAW_STATE_DIR points somewhere inside the repo; walk up to find a repo root.
  if (process.env.OPENCLAW_STATE_DIR) {
    addBase(process.env.OPENCLAW_STATE_DIR);
    let dir = process.env.OPENCLAW_STATE_DIR;
    for (let i = 0; i < 6; i++) {
      dir = path.dirname(dir);
      if (!dir || dir === path.dirname(dir)) break;
      addBase(dir);
    }
  }

  addBase(process.cwd());

  // Walk up from this script looking for a dir that contains openclaw/node_modules.
  let dir = __dirname;
  for (let i = 0; i < 10; i++) {
    addBase(dir);
    const parent = path.dirname(dir);
    if (!parent || parent === dir) break;
    dir = parent;
  }

  for (const c of candidates) {
    try {
      if (fs.existsSync(c)) return require(c);
    } catch (_) {
      /* try next candidate */
    }
  }

  throw new Error(
    "playwright-core not found. Tried standard require and candidate dirs:\n" +
      candidates.map((c) => "  - " + c).join("\n") +
      "\nSet OPENCLAW_HOME or install playwright-core so it can be resolved."
  );
}

/**
 * Find an installed chromium executable without trusting a version number.
 * chromium.executablePath() can report a version that doesn't match what's
 * actually on disk, so we glob the browsers cache instead.
 * Returns an absolute path to a chrome binary, or null if none found
 * (caller then lets playwright pick its own default).
 */
function findChromium() {
  const base =
    process.env.PLAYWRIGHT_BROWSERS_PATH ||
    path.join(os.homedir(), ".cache", "ms-playwright");

  let entries;
  try {
    entries = fs.readdirSync(base);
  } catch (_) {
    return null;
  }

  const relCandidates = [
    path.join("chrome-linux64", "chrome"),
    path.join("chrome-linux", "chrome"),
    path.join("chrome-mac", "Chromium.app", "Contents", "MacOS", "Chromium"),
  ];

  for (const entry of entries) {
    if (!entry.startsWith("chromium")) continue;
    for (const rel of relCandidates) {
      const full = path.join(base, entry, rel);
      if (fs.existsSync(full)) return full;
    }
  }

  return null;
}

function parseArgs(argv) {
  let dataStr = null;
  let outputPath = null;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--data" && argv[i + 1]) dataStr = argv[++i];
    else if ((argv[i] === "--output" || argv[i] === "-o") && argv[i + 1])
      outputPath = argv[++i];
  }
  return { dataStr, outputPath };
}

async function main() {
  const { dataStr: cliData, outputPath } = parseArgs(process.argv.slice(2));

  if (!outputPath) {
    throw new Error("missing --output <path>");
  }

  // Prefer --data, else read JSON from stdin.
  const dataStr = cliData || fs.readFileSync(0, "utf8");
  const data = JSON.parse(dataStr); // validate it's JSON; injected verbatim below

  // Template lives next to this script: ../assets/meal-card.html
  const templatePath = path.join(__dirname, "..", "assets", "meal-card.html");
  let html = fs.readFileSync(templatePath, "utf8");
  html = html.replace(
    "const D = window.__DATA__;",
    "const D = " + JSON.stringify(data) + ";"
  );

  // Ensure output directory exists.
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });

  const { chromium } = resolvePlaywright();

  const launchOpts = { args: ["--no-sandbox", "--force-color-profile=srgb"] };
  const chromePath = findChromium();
  if (chromePath) launchOpts.executablePath = chromePath; // else let playwright find its own

  const browser = await chromium.launch(launchOpts);
  try {
    const page = await browser.newPage({ deviceScaleFactor: 2 });
    await page.setContent(html, { waitUntil: "networkidle" });
    const card = await page.$("#card");
    if (!card) throw new Error("#card element not found in template");
    await card.screenshot({ path: outputPath });
  } finally {
    await browser.close();
  }

  console.log(outputPath);
}

main().catch((err) => {
  console.error(err && err.message ? err.message : String(err));
  process.exit(1);
});
