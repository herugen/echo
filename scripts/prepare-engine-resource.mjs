import { cp, rm, mkdir } from 'node:fs/promises';
import { existsSync, lstatSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const engine = path.join(root, 'packages', 'engine');
const target = path.join(root, 'apps', 'desktop', 'bundle-resources', 'engine');
const includeVenv = process.argv.includes('--include-venv') || process.env.ECHO_BUNDLE_VENV === '1';

function filter(source) {
  const base = path.basename(source);
  if (base === '__pycache__' || base === '.pytest_cache') return false;
  if (base.endsWith('.pyc') || base.endsWith('.pyo') || base.endsWith('.tmp')) return false;
  return true;
}

await rm(target, { recursive: true, force: true });
await mkdir(target, { recursive: true });
await cp(path.join(engine, 'src'), path.join(target, 'src'), { recursive: true, filter });
await cp(path.join(engine, 'pyproject.toml'), path.join(target, 'pyproject.toml'));

const binDir = path.join(engine, 'bin');
if (existsSync(binDir)) {
  await cp(binDir, path.join(target, 'bin'), { recursive: true, filter });
}

const venv = path.join(engine, '.venv');
if (includeVenv) {
  if (!existsSync(venv)) {
    throw new Error(`Cannot include venv; not found: ${venv}`);
  }
  const pythonPath = process.platform === 'win32'
    ? path.join(venv, 'Scripts', 'python.exe')
    : path.join(venv, 'bin', 'python');
  if (existsSync(pythonPath) && lstatSync(pythonPath).isSymbolicLink()) {
    throw new Error(`The venv Python is a symlink and is not portable: ${pythonPath}. Recreate the venv with: python -m venv --copies .venv`);
  }
  await cp(venv, path.join(target, '.venv'), { recursive: true, filter });
}

console.log(`Prepared engine resource at ${target}`);
console.log(`Included venv: ${includeVenv ? 'yes' : 'no'}`);
