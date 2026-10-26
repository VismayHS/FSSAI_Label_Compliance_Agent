// Add a React Bits component (TS + CSS flavor) from the commit pinned in tools/skills/manifest.json.
//   npm run add:react-bits -- StatusMark [CallChip ...]
// Writes src/components/reactbits/<Name>/, with a licence + source header on every file, and prints the
// npm dependencies to install with exact versions. See tools/skills/project/react-bits/SKILL.md.
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const manifest = JSON.parse(await readFile(resolve(here, "../../../tools/skills/manifest.json"), "utf8"));
const { repo, commit } = manifest.sources["react-bits"];
const raw = repo.replace("https://github.com/", "https://raw.githubusercontent.com/");

const names = process.argv.slice(2);
if (names.length === 0 || names.some((n) => !/^[A-Z][A-Za-z0-9]+$/.test(n))) {
  console.error("usage: npm run add:react-bits -- <ComponentName> [...]   (see tools/skills/vendor/react-bits/CATALOG.md)");
  process.exit(1);
}

const deps = new Set();
for (const name of names) {
  const url = `${raw}/${commit}/public/r/${name}-TS-CSS.json`;
  const res = await fetch(url);
  if (!res.ok) {
    console.error(`${name}: ${res.status} from ${url}`);
    process.exit(1);
  }
  const item = await res.json();
  const header = `React Bits ${item.title} (TS-CSS), ${repo} @ ${commit.slice(0, 7)}. MIT + Commons Clause, see tools/skills/vendor/react-bits/LICENSE.md.`;
  for (const file of item.files) {
    const out = join(here, "..", "src", "components", "reactbits", name, file.path.split("/").pop());
    await mkdir(dirname(out), { recursive: true });
    const comment = out.endsWith(".css") ? `/* ${header} */\n` : `// ${header}\n`;
    await writeFile(out, comment + file.content.replace(/^\s*['"]use client['"];?\s*\n/, ""), "utf8");
    console.log(`wrote ${out}`);
  }
  for (const dep of item.dependencies ?? []) deps.add(dep);
}
if (deps.size) console.log(`\nInstall: npm i -E ${[...deps].map((d) => d.replace(/@\^/, "@")).join(" ")}`);
