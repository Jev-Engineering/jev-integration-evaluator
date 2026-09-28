// Trusted synthetic entrypoint probe. Run only after explicit host execution grant.
'use strict';
const fs = require('node:fs');
const {pathToFileURL} = require('node:url');

async function main() {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  const moduleValue = input.format === 'commonjs'
    ? require(input.module)
    : await import(pathToFileURL(input.module).href);
  const entry = input.format === 'commonjs'
    ? (typeof moduleValue === 'function' ? moduleValue : moduleValue[input.symbol])
    : moduleValue[input.symbol];
  const events = moduleValue.events;
  if (typeof entry !== 'function' || !Array.isArray(events)) throw Error('reviewed_entrypoint_missing');
  const rows = [];
  const effects = [];
  globalThis.__jev_probe_effect = (...args) => { effects.push(structuredClone(args)); };
  for (const item of input.cases) {
    events.length = 0;
    effects.length = 0;
    let result = null; let exception = null;
    try { result = await entry(item.request); }
    catch (error) { exception = error?.name || 'Error'; }
    rows.push({id: item.id, result, exception, events: structuredClone(events),
      effects: structuredClone(effects)});
  }
  process.stdout.write(JSON.stringify({results: rows}) + '\n');
}
main().catch(() => { process.stderr.write('trusted_probe_failed\n'); process.exitCode = 2; });
