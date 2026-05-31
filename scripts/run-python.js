#!/usr/bin/env node
"use strict";

const childProcess = require("node:child_process");
const { findPython } = require("../bin/xengineer-pr-review.js");

function main(argv = process.argv.slice(2), options = {}) {
  const spawnSync = options.spawnSync || childProcess.spawnSync;
  const env = options.env || process.env;
  const python = findPython({ env, spawnSync });
  const result = spawnSync(python, argv, {
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
    process.exit(main());
  } catch (error) {
    console.error(`run-python: ${error.message}`);
    process.exit(1);
  }
}

module.exports = { main };
