// eslint-disable-next-line @typescript-eslint/no-var-requires
import { getEngineName } from '@waha/config';

import { WAHAEnvironment } from './structures/environment.dto';

// eslint-disable-next-line @typescript-eslint/no-var-requires
const fs = require('fs');

export enum WAHAVersion {
  PLUS = 'PLUS',
  CORE = 'CORE',
}

export function getWAHAVersion(): WAHAVersion {
  // force core version if env variables set
  const waha_version = process.env.WAHA_VERSION;
  if (waha_version && waha_version === WAHAVersion.CORE) {
    return WAHAVersion.CORE;
  }

  // Check the plus directory exists
  const plusExists = fs.existsSync(`${__dirname}/plus`);
  if (plusExists) {
    return WAHAVersion.PLUS;
  }

  return WAHAVersion.CORE;
}

export function getWorker() {
  return { id: process.env.WAHA_WORKER_ID || null };
}

function getPlatform() {
  return `${process.platform}/${process.arch}`;
}

export const VERSION: WAHAEnvironment = {
  version: '2026.2.1',
  engine: getEngineName(),
  tier: getWAHAVersion(),
  browser: null,
  platform: getPlatform(),
  worker: getWorker(),
};

export { getEngineName };
