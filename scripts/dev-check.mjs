import fs from 'node:fs';
import path from 'node:path';

const REQUIRED_DIRECTORIES = [
  'apps/desktop',
  'core',
  'adapters/unity',
  'adapters/godot',
  'integrations/mcp',
  'integrations/rest-api',
  'integrations/websocket',
  'integrations/ai-providers',
  'sdk',
  'tools',
  'tests',
  'docs',
  'config',
  'scripts',
];

const missing = REQUIRED_DIRECTORIES.filter(
  (dir) => !fs.existsSync(path.resolve(process.cwd(), dir))
);

if (missing.length > 0) {
  console.error('Missing required NEXUS architectural directories:', missing);
  process.exit(1);
}

console.log(`Verified ${REQUIRED_DIRECTORIES.length} architectural directories.`);
