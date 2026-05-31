#!/usr/bin/env node
"use strict";

const childProcess = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const MIN_PYTHON = { major: 3, minor: 12 };
const PACKAGE_ROOT = path.resolve(__dirname, "..");

function parsePythonVersion(output) {
  const match = /Python\s+(\d+)\.(\d+)(?:\.(\d+))?/.exec(output);
  if (!match) {
    return null;
  }
  return {
    major: Number.parseInt(match[1], 10),
    minor: Number.parseInt(match[2], 10),
    patch: Number.parseInt(match[3] || "0", 10),
  };
}

function isSupportedPython(version) {
  if (!version) {
    return false;
  }
  if (version.major !== MIN_PYTHON.major) {
    return version.major > MIN_PYTHON.major;
  }
  return version.minor >= MIN_PYTHON.minor;
}

function pythonCandidates(env = process.env) {
  const candidates = [
    env.XENGINEER_PYTHON,
    "python3.12",
    "python3",
    "python",
  ].filter(Boolean);
  return Array.from(new Set(candidates));
}

function findPython(options = {}) {
  const env = options.env || process.env;
  const spawnSync = options.spawnSync || childProcess.spawnSync;

  for (const candidate of pythonCandidates(env)) {
    const result = spawnSync(candidate, ["--version"], { encoding: "utf8" });
    if (result.error || result.status !== 0) {
      continue;
    }
    const version = parsePythonVersion(`${result.stdout || ""}\n${result.stderr || ""}`);
    if (isSupportedPython(version)) {
      return candidate;
    }
  }

  throw new Error(
    "Python 3.12+ is required. Install Python 3.12 or set XENGINEER_PYTHON=/path/to/python.",
  );
}

function cacheBase(env = process.env, platform = process.platform) {
  if (env.XENGINEER_CACHE_DIR) {
    return env.XENGINEER_CACHE_DIR;
  }
  if (env.XDG_CACHE_HOME) {
    return env.XDG_CACHE_HOME;
  }
  if (platform === "win32") {
    return env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
  }
  if (platform === "darwin") {
    return path.join(os.homedir(), "Library", "Caches");
  }
  return path.join(os.homedir(), ".cache");
}

function venvPythonPath(venvDir, platform = process.platform) {
  if (platform === "win32") {
    return path.join(venvDir, "Scripts", "python.exe");
  }
  return path.join(venvDir, "bin", "python");
}

function packageVersion(packageRoot = PACKAGE_ROOT) {
  const packageJsonPath = path.join(packageRoot, "package.json");
  const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
  return packageJson.version;
}

function isEditableSource(packageRoot = PACKAGE_ROOT) {
  return fs.existsSync(path.join(packageRoot, ".git"));
}

function markerContent(packageRoot, version, editable) {
  const marker = {
    version,
    editable,
    minPython: `${MIN_PYTHON.major}.${MIN_PYTHON.minor}`,
  };
  if (editable) {
    marker.packageRoot = path.resolve(packageRoot);
  } else {
    marker.packageFingerprint = packageFingerprint(packageRoot);
  }
  return JSON.stringify(marker);
}

function packageFingerprint(packageRoot) {
  const hash = crypto.createHash("sha256");
  for (const filePath of packageFingerprintFiles(packageRoot)) {
    hash.update(path.relative(packageRoot, filePath));
    hash.update("\0");
    hash.update(fs.readFileSync(filePath));
    hash.update("\0");
  }
  return hash.digest("hex");
}

function packageFingerprintFiles(packageRoot) {
  const files = [];
  for (const relativePath of ["package.json", "pyproject.toml"]) {
    const filePath = path.join(packageRoot, relativePath);
    if (fs.existsSync(filePath)) {
      files.push(filePath);
    }
  }
  collectPythonFiles(path.join(packageRoot, "src", "xengineer_pr_review"), files);
  return files.sort();
}

function collectPythonFiles(directory, files) {
  if (!fs.existsSync(directory)) {
    return;
  }
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      collectPythonFiles(entryPath, files);
    } else if (entry.isFile() && entry.name.endsWith(".py")) {
      files.push(entryPath);
    }
  }
}

function spawnChecked(command, args, label, options) {
  const result = options.spawnSync(command, args, {
    encoding: "utf8",
    env: options.env,
  });
  const stderr = options.stderr || process.stderr;
  if (result.stdout) {
    stderr.write(result.stdout);
  }
  if (result.stderr) {
    stderr.write(result.stderr);
  }
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`Failed to ${label} (${spawnFailureDetail(result)}).`);
  }
}

function spawnFailureDetail(result) {
  if (result.status !== null && result.status !== undefined) {
    return `exit ${result.status}`;
  }
  if (result.signal) {
    return `signal ${result.signal}`;
  }
  return "exit unknown";
}

function isVenvHealthy(pythonPath, env, spawnSync) {
  const result = spawnSync(pythonPath, ["-c", "import xengineer_pr_review"], {
    encoding: "utf8",
    env,
  });
  return !result.error && result.status === 0;
}

function ensureVenv(options = {}) {
  const env = options.env || process.env;
  const platform = options.platform || process.platform;
  const arch = options.arch || process.arch;
  const packageRoot = options.packageRoot || PACKAGE_ROOT;
  const spawnSync = options.spawnSync || childProcess.spawnSync;
  const stderr = options.stderr || process.stderr;
  const version = packageVersion(packageRoot);
  const editable = isEditableSource(packageRoot);
  const venvDir = path.join(
    cacheBase(env, platform),
    "xengineer-pr-review",
    `npm-${version}-${platform}-${arch}`,
    "venv",
  );
  const pythonPath = venvPythonPath(venvDir, platform);
  const markerPath = path.join(venvDir, ".xengineer-install.json");
  const expectedMarker = markerContent(packageRoot, version, editable);

  if (fs.existsSync(pythonPath) && fs.existsSync(markerPath)) {
    const currentMarker = fs.readFileSync(markerPath, "utf8");
    if (currentMarker === expectedMarker && isVenvHealthy(pythonPath, env, spawnSync)) {
      return pythonPath;
    }
    fs.rmSync(venvDir, { recursive: true, force: true });
  }

  const python = findPython({ env, spawnSync });
  fs.mkdirSync(path.dirname(venvDir), { recursive: true });
  if (!fs.existsSync(pythonPath)) {
    stderr.write("Creating XEngineer Python environment...\n");
    spawnChecked(python, ["-m", "venv", venvDir], "create Python virtual environment", {
      env,
      spawnSync,
      stderr,
    });
  }

  const pipArgs = ["-m", "pip", "install", "--require-virtualenv"];
  if (editable) {
    pipArgs.push("-e", packageRoot);
  } else {
    pipArgs.push("--upgrade", packageRoot);
  }
  stderr.write("Installing XEngineer Python dependencies...\n");
  spawnChecked(pythonPath, pipArgs, "install XEngineer Python package", {
    env,
    spawnSync,
    stderr,
  });

  fs.writeFileSync(markerPath, expectedMarker);
  return pythonPath;
}

function run(argv = process.argv.slice(2), options = {}) {
  const env = options.env || process.env;
  const spawnSync = options.spawnSync || childProcess.spawnSync;
  const pythonPath = ensureVenv({ ...options, env, spawnSync });
  const result = spawnSync(pythonPath, ["-m", "xengineer_pr_review", ...argv], {
    env,
    stdio: "inherit",
  });
  if (result.error) {
    throw result.error;
  }
  return result.status ?? 1;
}

if (require.main === module) {
  try {
    process.exit(run());
  } catch (error) {
    console.error(`xengineer-pr-review: ${error.message}`);
    process.exit(1);
  }
}

module.exports = {
  cacheBase,
  ensureVenv,
  findPython,
  isSupportedPython,
  parsePythonVersion,
  pythonCandidates,
  run,
  venvPythonPath,
};
