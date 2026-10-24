// Capture review screenshots of the running web client: a fold and a full page at desktop, tablet and phone.
//   node services/web/scripts/capture.mjs <outDir> <name>=<url>[|<css selector to click>...] [...]
// Writes <outDir>/<name>-desktop.png, -desktop-full.png, -tablet*, -mobile* (plus desktop.png / mobile.png for
// the first name, the files impeccable's finish review expects). Uses taste-skill's Chrome driver (Node 22+).
import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { Browser, sleep } from "../../../skills/vendor/taste-skill/skills/taste-skill/scripts/lib/cdp.mjs";

const [outDir, ...targets] = process.argv.slice(2);
if (!outDir || targets.length === 0) {
  console.error("usage: node capture.mjs <outDir> <name>=<url> [...]");
  process.exit(1);
}
mkdirSync(outDir, { recursive: true });
const VIEWPORTS = [["desktop", 1440, 900], ["tablet", 768, 1024], ["mobile", 390, 844]];

const browser = await Browser.launch();
try {
  for (const [i, target] of targets.entries()) {
    const [name, rest] = target.split(/=(.*)/s);
    const [url, ...clicks] = rest.split("|");
    for (const [label, width, height] of VIEWPORTS) {
      const page = await browser.newPage({ width, height, mobile: width < 600 });
      await page.goto(url, { timeoutMs: 30000, settleMs: 800 });
      await page.eval("document.fonts.ready.then(() => true)");
      await sleep(2500); // polling settles and entrance motion finishes before the capture
      for (const selector of clicks) {
        await page.eval(`document.querySelector(${JSON.stringify(selector)}).click(), true`);
        await sleep(300);
      }
      await page.screenshot({ path: join(outDir, `${name}-${label}.png`), format: "png" });
      await page.screenshot({ path: join(outDir, `${name}-${label}-full.png`), format: "png", fullPage: true });
      if (i === 0 && label !== "tablet") await page.screenshot({ path: join(outDir, `${label}.png`), format: "png", fullPage: true });
      await page.close();
      console.log(`captured ${name} @ ${label}`);
    }
  }
} finally {
  await browser.close();
}
