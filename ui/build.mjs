import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as esbuild from "esbuild";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.join(__dirname, "dist");
fs.mkdirSync(outDir, { recursive: true });

const result = await esbuild.build({
  entryPoints: [path.join(__dirname, "src", "app.ts")],
  bundle: true,
  minify: true,
  format: "iife",
  platform: "browser",
  target: ["es2022"],
  write: false,
});

// Escape closing script sequences so HTML parser never terminates <script> early.
const jsCode = result.outputFiles[0].text.replace(/<\/script/gi, "<\\/script");
const template = fs.readFileSync(path.join(__dirname, "template.html"), "utf8");
const placeholder = '<script type="module" src="./dist/bundle.js"></script>';

const idx = template.indexOf(placeholder);
if (idx === -1) {
  throw new Error("Placeholder script tag not found in template.html");
}

// Use slice concatenation instead of String.replace() so '$' sequences in JS are never interpreted.
const inlined =
  template.slice(0, idx) +
  `<script>\n${jsCode}\n</script>` +
  template.slice(idx + placeholder.length);

const scriptOpenCount = (inlined.match(/<script\b/gi) ?? []).length;
const scriptCloseCount = (inlined.match(/<\/script>/gi) ?? []).length;
if (scriptOpenCount !== 1 || scriptCloseCount !== 1) {
  throw new Error(`Unexpected script tag counts: open=${scriptOpenCount}, close=${scriptCloseCount}`);
}

const outHtml = path.join(outDir, "app.html");
fs.writeFileSync(outHtml, inlined, "utf8");
console.log(`Built ${outHtml} (${inlined.length} bytes, scripts=${scriptOpenCount}/${scriptCloseCount})`);
