// Explicit trusted TypeScript emit; never loads a target tsconfig or plugin.
'use strict';
const fs = require('node:fs');
const crypto = require('node:crypto');
const compiler = process.env.JEV_TRUSTED_TYPESCRIPT;
if (!compiler || !require('node:path').isAbsolute(compiler)) process.exit(3);
const ts = require(fs.realpathSync(compiler));
if (ts.version !== '5.8.3') process.exit(3);
try {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  if (Object.keys(input).sort().join('|') !== 'file|source' ||
      typeof input.source !== 'string' || !/^[A-Za-z_$][\w$-]*\.ts$/.test(input.file) ||
      Buffer.byteLength(input.source, 'utf8') > 500000) throw Error('invalid');
  const source = ts.createSourceFile(input.file, input.source, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TS);
  if (source.parseDiagnostics.length || source.statements.some(x => ts.isImportDeclaration(x))) throw Error('invalid');
  const out = ts.transpileModule(input.source, {fileName: input.file, reportDiagnostics: true,
    compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext,
      isolatedModules: true, importsNotUsedAsValues: ts.ImportsNotUsedAsValues.Remove}});
  if (out.diagnostics?.length) throw Error('invalid');
  process.stdout.write(JSON.stringify({source: out.outputText,
    sha256: crypto.createHash('sha256').update(out.outputText).digest('hex')}) + '\n');
} catch (_) { process.stderr.write('trusted_emit_failed\n'); process.exitCode = 2; }
