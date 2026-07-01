import { access } from "node:fs/promises";

const requiredFiles = [
  "index.html",
  "README.md",
  "ANALYSIS.md",
  "src/main.js",
  "src/levels.js",
  "src/motion.js",
  "src/state.js",
  "src/styles.css"
];

await Promise.all(requiredFiles.map((file) => access(file)));
console.log(`Static build check passed: ${requiredFiles.length} files present.`);
