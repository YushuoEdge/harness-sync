// Local source-build workaround for upstream revision 29628c9.
// Run: node harnesses/zcode/scripts/prepare_shared_dist.mjs /path/to/ZCode
// Changes only the supplied source checkout's shared package and dist tree.
import { readdir, readFile, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

if (process.argv.length !== 3) throw new Error("Pass the ZCode source checkout path");
const root = resolve(process.argv[2]);
const shared = join(root, "packages/shared");
const { build } = await import(pathToFileURL(join(root, "node_modules/esbuild/lib/main.js")));
async function sources(directory) {
  return (await Promise.all((await readdir(directory, { withFileTypes: true })).map(async entry => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? sources(path)
      : entry.name.endsWith(".ts") && !entry.name.endsWith(".d.ts") ? [path] : [];
  }))).flat();
}
await build({
  entryPoints: await sources(join(shared, "src")),
  outdir: join(shared, "dist"), outbase: join(shared, "src"),
  format: "esm", platform: "node", target: "node24", logLevel: "warning",
});
const path = join(shared, "package.json");
const manifest = JSON.parse(await readFile(path, "utf8"));
for (const key of Object.keys(manifest.exports)) {
  manifest.exports[key] = manifest.exports[key].replace("./src/", "./dist/").replace(/\.ts$/, ".js");
}
await writeFile(path, JSON.stringify(manifest, null, 2) + "\n");
