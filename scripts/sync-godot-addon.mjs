import fs from 'node:fs';
import path from 'node:path';

const REPO_ROOT = process.cwd();
const SOURCE_DIR = path.resolve(REPO_ROOT, 'adapters/godot/addons/nexus_bridge');
const TARGET_DIR = path.resolve(REPO_ROOT, 'adapters/godot/test_project/addons/nexus_bridge');

if (!fs.existsSync(SOURCE_DIR)) {
  console.error(`Missing source Godot addon directory: ${SOURCE_DIR}`);
  process.exit(1);
}

fs.mkdirSync(TARGET_DIR, { recursive: true });

for (const existing of fs.readdirSync(TARGET_DIR)) {
  const candidate = path.join(TARGET_DIR, existing);
  if (fs.statSync(candidate).isFile()) {
    fs.unlinkSync(candidate);
  }
}

let copiedCount = 0;
for (const entry of fs.readdirSync(SOURCE_DIR)) {
  const srcPath = path.join(SOURCE_DIR, entry);
  const dstPath = path.join(TARGET_DIR, entry);
  if (fs.statSync(srcPath).isFile()) {
    fs.copyFileSync(srcPath, dstPath);
    copiedCount += 1;
  }
}

console.log(
  `Synced ${copiedCount} Godot nexus_bridge addon files to adapters/godot/test_project/addons/nexus_bridge/.`
);
