const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const wrapper = require("../bin/xengineer-pr-review.js");

function makePackageRoot({ editable = true } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "xengineer-wrapper-"));
  fs.writeFileSync(
    path.join(root, "package.json"),
    JSON.stringify({ name: "xengineer-pr-review", version: "9.8.7" }),
  );
  if (editable) {
    fs.writeFileSync(path.join(root, ".git"), "gitdir: /tmp/example\n");
  }
  return root;
}

test("findPython prefers XENGINEER_PYTHON when it points at Python 3.12+", () => {
  const calls = [];
  const spawnSync = (command, args) => {
    calls.push([command, args]);
    if (command === "/custom/python") {
      return { status: 0, stdout: "Python 3.12.4\n", stderr: "" };
    }
    return { status: 0, stdout: "Python 3.11.9\n", stderr: "" };
  };

  const python = wrapper.findPython({
    env: { XENGINEER_PYTHON: "/custom/python" },
    spawnSync,
  });

  assert.equal(python, "/custom/python");
  assert.deepEqual(calls[0], ["/custom/python", ["--version"]]);
});

test("findPython skips unsupported interpreters and selects python3.12", () => {
  const seen = [];
  const spawnSync = (command) => {
    seen.push(command);
    if (command === "python3.12") {
      return { status: 0, stdout: "Python 3.12.3\n", stderr: "" };
    }
    return { status: 0, stdout: "Python 3.11.9\n", stderr: "" };
  };

  assert.equal(
    wrapper.findPython({ env: { XENGINEER_PYTHON: "/old/python" }, spawnSync }),
    "python3.12",
  );
  assert.deepEqual(seen, ["/old/python", "python3.12"]);
});

test("ensureVenv creates a cached venv and installs local source editably", () => {
  const packageRoot = makePackageRoot();
  const cacheRoot = fs.mkdtempSync(path.join(os.tmpdir(), "xengineer-cache-"));
  const calls = [];
  const spawnSync = (command, args) => {
    calls.push([command, args]);
    if (args[0] === "--version") {
      return { status: 0, stdout: "Python 3.12.3\n", stderr: "" };
    }
    if (args[0] === "-m" && args[1] === "venv") {
      const pythonPath = wrapper.venvPythonPath(args[2], process.platform);
      fs.mkdirSync(path.dirname(pythonPath), { recursive: true });
      fs.writeFileSync(pythonPath, "");
    }
    return { status: 0, stdout: "", stderr: "" };
  };

  const pythonPath = wrapper.ensureVenv({
    env: { XENGINEER_CACHE_DIR: cacheRoot },
    packageRoot,
    spawnSync,
  });

  assert.equal(pythonPath, wrapper.venvPythonPath(path.dirname(path.dirname(pythonPath))));
  assert.deepEqual(calls[0], ["python3.12", ["--version"]]);
  assert.equal(calls[1][1][0], "-m");
  assert.equal(calls[1][1][1], "venv");
  assert.deepEqual(calls[2][1], ["-m", "pip", "install", "-e", packageRoot]);
});

test("run forwards user arguments to the Python module inside the cached venv", () => {
  const packageRoot = makePackageRoot();
  const cacheRoot = fs.mkdtempSync(path.join(os.tmpdir(), "xengineer-cache-"));
  const calls = [];
  const spawnSync = (command, args) => {
    calls.push([command, args]);
    if (args[0] === "--version") {
      return { status: 0, stdout: "Python 3.12.3\n", stderr: "" };
    }
    if (args[0] === "-m" && args[1] === "venv") {
      const pythonPath = wrapper.venvPythonPath(args[2], process.platform);
      fs.mkdirSync(path.dirname(pythonPath), { recursive: true });
      fs.writeFileSync(pythonPath, "");
    }
    return { status: 0, stdout: "", stderr: "" };
  };

  const status = wrapper.run(["--judge-demo", "--output", "-"], {
    env: { XENGINEER_CACHE_DIR: cacheRoot },
    packageRoot,
    spawnSync,
  });

  const finalCall = calls.at(-1);
  assert.deepEqual(finalCall[1], [
    "-m",
    "xengineer_pr_review",
    "--judge-demo",
    "--output",
    "-",
  ]);
  assert.equal(status, 0);
});

test("ensureVenv reuses published package cache for the same version", () => {
  const firstPackageRoot = makePackageRoot({ editable: false });
  const secondPackageRoot = makePackageRoot({ editable: false });
  const cacheRoot = fs.mkdtempSync(path.join(os.tmpdir(), "xengineer-cache-"));
  const calls = [];
  const spawnSync = (command, args) => {
    calls.push([command, args]);
    if (args[0] === "--version") {
      return { status: 0, stdout: "Python 3.12.3\n", stderr: "" };
    }
    if (args[0] === "-m" && args[1] === "venv") {
      const pythonPath = wrapper.venvPythonPath(args[2], process.platform);
      fs.mkdirSync(path.dirname(pythonPath), { recursive: true });
      fs.writeFileSync(pythonPath, "");
    }
    return { status: 0, stdout: "", stderr: "" };
  };

  const firstPython = wrapper.ensureVenv({
    env: { XENGINEER_CACHE_DIR: cacheRoot },
    packageRoot: firstPackageRoot,
    spawnSync,
  });
  calls.length = 0;
  const secondPython = wrapper.ensureVenv({
    env: { XENGINEER_CACHE_DIR: cacheRoot },
    packageRoot: secondPackageRoot,
    spawnSync,
  });

  assert.equal(secondPython, firstPython);
  assert.deepEqual(calls, [
    [firstPython, ["-c", "import xengineer_pr_review"]],
  ]);
});

test("ensureVenv sends setup command output to stderr instead of inherited stdout", () => {
  const packageRoot = makePackageRoot();
  const cacheRoot = fs.mkdtempSync(path.join(os.tmpdir(), "xengineer-cache-"));
  const setupOptions = [];
  const stderrChunks = [];
  const stderr = {
    write(chunk) {
      stderrChunks.push(chunk);
    },
  };
  const spawnSync = (command, args, options) => {
    if (args[0] !== "--version") {
      setupOptions.push(options);
    }
    if (args[0] === "--version") {
      return { status: 0, stdout: "Python 3.12.3\n", stderr: "" };
    }
    if (args[0] === "-m" && args[1] === "venv") {
      const pythonPath = wrapper.venvPythonPath(args[2], process.platform);
      fs.mkdirSync(path.dirname(pythonPath), { recursive: true });
      fs.writeFileSync(pythonPath, "");
    }
    return { status: 0, stdout: "setup stdout\n", stderr: "setup stderr\n" };
  };

  wrapper.ensureVenv({
    env: { XENGINEER_CACHE_DIR: cacheRoot },
    packageRoot,
    spawnSync,
    stderr,
  });

  assert.equal(setupOptions.length, 2);
  assert(setupOptions.every((options) => options.encoding === "utf8"));
  assert.equal(
    stderrChunks.join(""),
    "setup stdout\nsetup stderr\nsetup stdout\nsetup stderr\n",
  );
});

test("ensureVenv repairs a cached venv when the installed package is not importable", () => {
  const packageRoot = makePackageRoot();
  const cacheRoot = fs.mkdtempSync(path.join(os.tmpdir(), "xengineer-cache-"));
  let failNextHealthCheck = false;
  const calls = [];
  const spawnSync = (command, args) => {
    calls.push([command, args]);
    if (args[0] === "--version") {
      return { status: 0, stdout: "Python 3.12.3\n", stderr: "" };
    }
    if (args[0] === "-c" && args[1] === "import xengineer_pr_review") {
      if (failNextHealthCheck) {
        failNextHealthCheck = false;
        return { status: 1, stdout: "", stderr: "missing package\n" };
      }
      return { status: 0, stdout: "", stderr: "" };
    }
    if (args[0] === "-m" && args[1] === "venv") {
      const pythonPath = wrapper.venvPythonPath(args[2], process.platform);
      fs.mkdirSync(path.dirname(pythonPath), { recursive: true });
      fs.writeFileSync(pythonPath, "");
    }
    return { status: 0, stdout: "", stderr: "" };
  };

  const firstPython = wrapper.ensureVenv({
    env: { XENGINEER_CACHE_DIR: cacheRoot },
    packageRoot,
    spawnSync,
  });
  failNextHealthCheck = true;
  calls.length = 0;

  const secondPython = wrapper.ensureVenv({
    env: { XENGINEER_CACHE_DIR: cacheRoot },
    packageRoot,
    spawnSync,
  });

  assert.equal(secondPython, firstPython);
  assert(calls.some(([, args]) => args.join(" ") === "-c import xengineer_pr_review"));
  assert(calls.some(([, args]) => args.join(" ") === "-m venv " + path.dirname(path.dirname(firstPython))));
  assert(calls.some(([, args]) => args.join(" ") === "-m pip install -e " + packageRoot));
});

test("ensureVenv includes termination signal details in setup failures", () => {
  const packageRoot = makePackageRoot();
  const cacheRoot = fs.mkdtempSync(path.join(os.tmpdir(), "xengineer-cache-"));
  const spawnSync = (command, args) => {
    if (args[0] === "--version") {
      return { status: 0, stdout: "Python 3.12.3\n", stderr: "" };
    }
    if (args[0] === "-m" && args[1] === "venv") {
      const pythonPath = wrapper.venvPythonPath(args[2], process.platform);
      fs.mkdirSync(path.dirname(pythonPath), { recursive: true });
      fs.writeFileSync(pythonPath, "");
      return { status: 0, stdout: "", stderr: "" };
    }
    return { status: null, signal: "SIGTERM", stdout: "", stderr: "" };
  };

  assert.throws(
    () =>
      wrapper.ensureVenv({
        env: { XENGINEER_CACHE_DIR: cacheRoot },
        packageRoot,
        spawnSync,
      }),
    /SIGTERM/,
  );
});
