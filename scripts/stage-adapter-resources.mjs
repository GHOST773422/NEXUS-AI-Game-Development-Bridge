import fs from 'node:fs';
import path from 'node:path';

const REPO_ROOT = process.cwd();
const TARGET_ROOT = path.resolve(REPO_ROOT, 'apps/desktop/src-tauri/resources/adapters');

function copyRecursive(src, dst, excludeDirs = new Set()) {
  if (!fs.existsSync(src)) {
    throw new Error(`Missing adapter source path: ${src}`);
  }
  const stat = fs.statSync(src);
  if (stat.isDirectory()) {
    const baseName = path.basename(src);
    if (excludeDirs.has(baseName)) {
      return 0;
    }
    fs.mkdirSync(dst, { recursive: true });
    let count = 0;
    for (const entry of fs.readdirSync(src)) {
      count += copyRecursive(path.join(src, entry), path.join(dst, entry), excludeDirs);
    }
    return count;
  }
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.copyFileSync(src, dst);
  return 1;
}

fs.rmSync(TARGET_ROOT, { recursive: true, force: true });
fs.mkdirSync(TARGET_ROOT, { recursive: true });

let totalFiles = 0;

// Stage Unity UPM package (exclude test_project artifacts).
const unitySrc = path.resolve(REPO_ROOT, 'adapters/unity');
const unityDst = path.resolve(TARGET_ROOT, 'unity');
const unityExcluded = new Set(['test_project', 'Temp', 'Library', 'Logs', 'obj', 'bin']);
for (const entry of fs.readdirSync(unitySrc)) {
  if (unityExcluded.has(entry)) continue;
  totalFiles += copyRecursive(path.join(unitySrc, entry), path.join(unityDst, entry), unityExcluded);
}

// Stage Godot EditorPlugin addon + manifest + guide.
const godotAddonSrc = path.resolve(REPO_ROOT, 'adapters/godot/addons/nexus_bridge');
const godotAddonDst = path.resolve(TARGET_ROOT, 'godot/addons/nexus_bridge');
totalFiles += copyRecursive(godotAddonSrc, godotAddonDst);

for (const metaFile of ['nexus-adapter.manifest.json', 'README.md']) {
  const srcFile = path.resolve(REPO_ROOT, 'adapters/godot', metaFile);
  if (fs.existsSync(srcFile)) {
    totalFiles += copyRecursive(srcFile, path.resolve(TARGET_ROOT, 'godot', metaFile));
  }
}

console.log(
  `Staged ${totalFiles} Unity and Godot adapter files into apps/desktop/src-tauri/resources/adapters/.`
);
