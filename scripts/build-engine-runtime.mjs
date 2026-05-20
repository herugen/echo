import { cp, mkdir, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const engine = path.join(root, 'packages', 'engine');
const target = path.join(root, 'apps', 'desktop', 'bundle-resources', 'engine');
const cache = path.join(root, '.cache', 'python-build-standalone');

const PBS_RELEASE = process.env.ECHO_PYTHON_STANDALONE_RELEASE || '20260510';
const PYTHON_VERSION = process.env.ECHO_PYTHON_STANDALONE_VERSION || '3.10.20';
const WINDOWS_CUDA_ENABLED = process.platform === 'win32' && process.env.ECHO_WINDOWS_CUDA !== '0';
const PYTORCH_CUDA_INDEX = process.env.ECHO_PYTORCH_CUDA_INDEX || 'https://download.pytorch.org/whl/cu128';
const WINDOWS_CUDA_PACKAGES = [
  'nvidia-cuda-runtime-cu12==12.8.90',
  'nvidia-cuda-nvrtc-cu12==12.8.93',
  'nvidia-cublas-cu12==12.8.4.1',
  'nvidia-cudnn-cu12==8.9.7.29',
];

function run(command, args, options = {}) {
  console.log(`$ ${[command, ...args].join(' ')}`);
  const result = spawnSync(command, args, { stdio: 'inherit', shell: process.platform === 'win32', ...options });
  if (result.status !== 0) {
    throw new Error(`${command} exited with status ${result.status}`);
  }
}

function filter(source) {
  const base = path.basename(source);
  if (base === '__pycache__' || base === '.pytest_cache' || base === '.venv') return false;
  if (base.endsWith('.pyc') || base.endsWith('.pyo') || base.endsWith('.tmp')) return false;
  return true;
}

function platformTriple() {
  if (process.platform === 'darwin' && process.arch === 'arm64') return 'aarch64-apple-darwin';
  if (process.platform === 'darwin' && process.arch === 'x64') return 'x86_64-apple-darwin';
  if (process.platform === 'win32' && process.arch === 'x64') return 'x86_64-pc-windows-msvc';
  throw new Error(`Unsupported packaging platform: ${process.platform}/${process.arch}`);
}

function archiveName() {
  return `cpython-${PYTHON_VERSION}+${PBS_RELEASE}-${platformTriple()}-install_only.tar.gz`;
}

function archiveUrl() {
  return process.env.ECHO_PYTHON_STANDALONE_URL || `https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_RELEASE}/${archiveName()}`;
}

function findPythonExecutable(runtimeDir) {
  const candidates = process.platform === 'win32'
    ? [
        path.join(runtimeDir, 'python', 'python.exe'),
        path.join(runtimeDir, 'python', 'install', 'python.exe'),
      ]
    : [
        path.join(runtimeDir, 'python', 'install', 'bin', 'python3'),
        path.join(runtimeDir, 'python', 'install', 'bin', 'python'),
        path.join(runtimeDir, 'python', 'bin', 'python3'),
        path.join(runtimeDir, 'python', 'bin', 'python'),
      ];
  const found = candidates.find((candidate) => existsSync(candidate));
  if (!found) {
    throw new Error(`Could not find Python executable under ${runtimeDir}`);
  }
  return found;
}

await rm(target, { recursive: true, force: true });
await mkdir(target, { recursive: true });

await mkdir(cache, { recursive: true });
const archive = path.join(cache, archiveName());
if (!existsSync(archive)) {
  run('curl', ['-L', archiveUrl(), '-o', archive]);
}

run('tar', ['-xzf', archive, '-C', target]);
const python = findPythonExecutable(target);
run(python, ['-m', 'ensurepip', '--upgrade'], { shell: false });
run(python, ['-m', 'pip', 'install', '-U', 'pip'], { shell: false });
if (WINDOWS_CUDA_ENABLED) {
  run(python, ['-m', 'pip', 'install', '-U', 'torch', '--index-url', PYTORCH_CUDA_INDEX], { shell: false });
  run(python, ['-m', 'pip', 'install', ...WINDOWS_CUDA_PACKAGES], { shell: false });
  run(python, ['-c', 'import torch; print(f"PyTorch {torch.__version__} CUDA {torch.version.cuda}"); assert torch.version.cuda, "Expected CUDA-enabled PyTorch"'], { shell: false });
}
run(python, ['-m', 'pip', 'install', engine], { shell: false });

const binDir = path.join(engine, 'bin');
if (existsSync(binDir)) {
  await cp(binDir, path.join(target, 'bin'), { recursive: true, filter });
}

console.log(`Prepared self-contained engine runtime at ${target}`);
console.log(`Python runtime: ${python}`);
console.log(`Windows CUDA runtime: ${WINDOWS_CUDA_ENABLED ? `enabled (${PYTORCH_CUDA_INDEX})` : 'disabled'}`);
console.log('End users do not need Python installed; only WhisperX model downloads may happen at runtime.');
