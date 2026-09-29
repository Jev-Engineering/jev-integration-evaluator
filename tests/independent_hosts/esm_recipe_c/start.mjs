import fs from 'node:fs';
import {seam} from './host.mjs';

if (process.env.JEV_RUNTIME_MODE !== 'off') throw Error('mode must remain off');
for (const key of ['NODE_EFFECT_PATH', 'NODE_READY_PATH', 'NODE_INTEGRATION_PATH']) {
  if (!process.env[key]) throw Error('missing reviewed output path');
}
globalThis.__jev_probe_effect = (action, item) => {
  fs.writeFileSync(process.env.NODE_EFFECT_PATH, action + ':' + item + '\n', {flag: 'wx'});
};

async function main() {
  const result = await seam({task_id: 'esm-task', invocation_id: 'esm-normal-v1',
                             item: 'alpha', permit: true});
  if (result !== 'read:alpha') throw Error('unexpected ESM result');
  fs.writeFileSync(process.env.NODE_READY_PATH, 'ready\n', {flag: 'wx'});
  fs.writeFileSync(process.env.NODE_INTEGRATION_PATH, 'integration\n', {flag: 'wx'});
  await new Promise(resolve => setTimeout(resolve, 800));
}
main().catch(() => { process.exitCode = 1; });
