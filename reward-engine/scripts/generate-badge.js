#!/usr/bin/env node
/**
 * generate-badge.js — Render badge card HTML to PNG using Puppeteer.
 *
 * Usage:
 *   node generate-badge.js --data '{"tagline":"...","badge_name":"...","data_pill":"...","subtitle":"...","username":"...","date":"..."}' --output /path/to/output.png
 *
 * Or pipe JSON via stdin:
 *   echo '{"tagline":"..."}' | node generate-badge.js --output /path/to/output.png
 */

const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');

async function main() {
  const args = process.argv.slice(2);
  let dataStr = null;
  let outputPath = null;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--data' && args[i + 1]) dataStr = args[++i];
    if (args[i] === '--output' && args[i + 1]) outputPath = args[++i];
    if (args[i] === '-o' && args[i + 1]) outputPath = args[++i];
  }

  // Read from stdin if no --data
  if (!dataStr) {
    dataStr = fs.readFileSync(0, 'utf8');
  }

  const data = JSON.parse(dataStr);

  if (!outputPath) {
    outputPath = path.join(__dirname, '..', 'output', 'badge.png');
  }

  // Ensure output dir exists
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });

  // Read template
  const templatePath = path.join(__dirname, '..', 'templates', 'badge-card.html');
  let html = fs.readFileSync(templatePath, 'utf8');

  // Inject data
  html = html.replace(
    /\/\*BADGE_DATA\*\/.*?\/\*END_DATA\*\//s,
    `/*BADGE_DATA*/ ${JSON.stringify(data)} /*END_DATA*/`
  );

  // Launch browser
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 700, height: 900, deviceScaleFactor: 2 });
  await page.setContent(html, { waitUntil: 'networkidle0' });

  // Get the card element bounds
  const cardEl = await page.$('.card');
  const box = await cardEl.boundingBox();

  // Screenshot just the card with transparent background
  await page.screenshot({
    path: outputPath,
    type: 'png',
    clip: {
      x: box.x - 10,
      y: box.y - 10,
      width: box.width + 20,
      height: box.height + 20,
    },
    omitBackground: true,
  });

  await browser.close();

  console.log(outputPath);
}

main().catch(err => {
  console.error(err.message);
  process.exit(1);
});
