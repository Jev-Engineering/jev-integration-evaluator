// Trusted-tooling-only bounded AST transform. Never read target configuration.
'use strict';
const fs = require('node:fs');
const crypto = require('node:crypto');
const path = require('node:path');
const compilerPath = process.env.JEV_TRUSTED_TYPESCRIPT;
if (!compilerPath || !path.isAbsolute(compilerPath) ||
    !/[\\/]typescript[\\/]lib[\\/]typescript\.js$/.test(compilerPath)) {
  process.stderr.write('trusted_typescript_compiler_required\n');
  process.exit(3);
}
const ts = require(fs.realpathSync(compilerPath));
if (ts.version !== '5.8.3') {
  process.stderr.write('unsupported_typescript_version\n');
  process.exit(3);
}

function refuse(code) { const error = new Error(code); error.code = code; throw error; }
function sha(text) { return crypto.createHash('sha256').update(text, 'utf8').digest('hex'); }
function identifier(text) { return typeof text === 'string' && /^[A-Za-z_$][\w$]*$/.test(text); }
function modifiers(node, kind) { return !!node.modifiers?.some(x => x.kind === kind); }
function nameOf(node) { return ts.isIdentifier(node) ? node.text : null; }
function diagnostics(rows) { return rows.map(x => ts.flattenDiagnosticMessageText(x.messageText, ' ')); }

function transform(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input) ||
      Object.keys(input).sort().join('|') !==
        ['adapter_alias', 'adapter_path', 'bindings', 'file', 'original', 'source', 'symbol'].sort().join('|') ||
      typeof input.source !== 'string' || Buffer.byteLength(input.source, 'utf8') > 500_000 ||
      !['.mjs', '.cjs', '.ts'].some(x => input.file?.endsWith(x)) ||
      !identifier(input.symbol) || !identifier(input.original) || !identifier(input.adapter_alias) ||
      input.symbol === input.original || input.adapter_alias === input.symbol ||
      input.adapter_alias === input.original ||
      !input.bindings || typeof input.bindings !== 'object' || Array.isArray(input.bindings) ||
      Object.keys(input.bindings).sort().join('|') !==
        ['registry', 'gate', 'validate', 'blocked', 'evidence', 'baseline_action'].sort().join('|') ||
      Object.values(input.bindings).some(x => !identifier(x)) ||
      typeof input.adapter_path !== 'string' ||
      !/^\.\/[A-Za-z_$][\w$-]*\.cjs$/.test(input.adapter_path))
    refuse('invalid_js_transform_request');
  const format = input.file.endsWith('.cjs') ? 'commonjs' : input.file.endsWith('.ts') ? 'typescript' : 'esm';
  const source = ts.createSourceFile(input.file, input.source, ts.ScriptTarget.ES2022, true,
    format === 'typescript' ? ts.ScriptKind.TS : ts.ScriptKind.JS);
  if (source.parseDiagnostics.length) refuse('unsupported_js_syntax');
  const selected = source.statements.filter(x => ts.isFunctionDeclaration(x) && x.name?.text === input.symbol);
  const originals = source.statements.filter(x => ts.isFunctionDeclaration(x) && x.name?.text === input.original);
  if (selected.length !== 1 || originals.length !== 1 ||
      source.statements.some(x => ts.isImportDeclaration(x) && x.importClause?.name?.text === input.adapter_alias))
    refuse('ambiguous_js_binding');
  const fn = selected[0];
  for (const name of Object.values(input.bindings)) {
    if (source.statements.filter(x => ts.isFunctionDeclaration(x) && x.name?.text === name).length !== 1)
      refuse('missing_js_host_binding');
  }
  if (!modifiers(fn, ts.SyntaxKind.AsyncKeyword) || modifiers(fn, ts.SyntaxKind.DefaultKeyword) ||
      fn.asteriskToken || fn.typeParameters?.length || fn.parameters.length !== 1 ||
      !ts.isIdentifier(fn.parameters[0].name) || fn.parameters[0].initializer ||
      fn.parameters[0].dotDotDotToken || !fn.body || fn.body.statements.length !== 1 ||
      !ts.isReturnStatement(fn.body.statements[0]) ||
      !ts.isAwaitExpression(fn.body.statements[0].expression) ||
      !ts.isCallExpression(fn.body.statements[0].expression.expression))
    refuse('unsupported_js_source_shape');
  const argument = fn.parameters[0].name.text;
  const call = fn.body.statements[0].expression.expression;
  if (nameOf(call.expression) !== input.original || call.arguments.length !== 1 ||
      nameOf(call.arguments[0]) !== argument || call.typeArguments?.length ||
      (format === 'typescript' && (!fn.parameters[0].type || !fn.type)))
    refuse('unsupported_js_source_shape');
  if (format !== 'commonjs' && !modifiers(fn, ts.SyntaxKind.ExportKeyword))
    refuse('selected_js_export_required');
  if (format === 'commonjs') {
    const exports = source.statements.filter(x => ts.isExpressionStatement(x) &&
      ts.isBinaryExpression(x.expression) && x.expression.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
      ((x.expression.left.getText(source) === 'module.exports') ||
       (x.expression.left.getText(source) === 'exports.' + input.symbol)));
    if (exports.length !== 1 || nameOf(exports[0].expression.right) !== input.symbol)
      refuse('selected_js_export_required');
  }
  let forbidden = false;
  const visit = node => {
    if (ts.isDecorator(node) || ts.isImportCall(node) || ts.isImportDeclaration(node) ||
        ts.isCallExpression(node) && nameOf(node.expression) === 'require' ||
        ts.isCallExpression(node) && ['eval', 'Function'].includes(nameOf(node.expression)) ||
        ts.isNewExpression(node) && nameOf(node.expression) === 'Function' ||
        ts.isIdentifier(node) && node.text === input.adapter_alias ||
        ts.isBinaryExpression(node) &&
          node.operatorToken.kind >= ts.SyntaxKind.FirstAssignment &&
          node.operatorToken.kind <= ts.SyntaxKind.LastAssignment &&
          [input.symbol, input.original].includes(nameOf(node.left)) ||
        ts.isPrefixUnaryExpression(node) && [input.symbol, input.original].includes(nameOf(node.operand)) ||
        ts.isPostfixUnaryExpression(node) && [input.symbol, input.original].includes(nameOf(node.operand)))
      forbidden = true;
    ts.forEachChild(node, visit);
  };
  visit(source);
  if (forbidden) refuse('unsupported_js_binding_or_syntax');
  const roles = Object.keys(input.bindings).sort();
  const bindings = roles.map(role => `${role}: ${input.bindings[role]}`).join(', ');
  const replacement = `${input.adapter_alias}.invoke(${input.original}, ${argument}, {${bindings}})`;
  let rewritten = input.source.slice(0, call.getStart(source)) + replacement + input.source.slice(call.end);
  const newline = input.source.includes('\r\n') ? '\r\n' : '\n';
  if (input.source.includes('\r') && !input.source.includes('\r\n')) refuse('unsupported_js_newline');
  const importLine = format === 'commonjs'
    ? `const ${input.adapter_alias} = require('${input.adapter_path}');${newline}`
    : `import ${input.adapter_alias} from '${input.adapter_path}';${newline}`;
  let insertion = 0;
  if (rewritten.startsWith('#!')) insertion = rewritten.indexOf('\n') + 1;
  // Keep directive prologues intact. In particular, inserting a require before
  // 'use strict' silently changes CommonJS execution semantics.
  for (const statement of source.statements) {
    if (!ts.isExpressionStatement(statement) || !ts.isStringLiteral(statement.expression)) break;
    insertion = statement.end;
  }
  rewritten = rewritten.slice(0, insertion) + importLine + rewritten.slice(insertion);
  const finalSource = ts.createSourceFile(input.file, rewritten, ts.ScriptTarget.ES2022, true,
    format === 'typescript' ? ts.ScriptKind.TS : ts.ScriptKind.JS);
  if (finalSource.parseDiagnostics.length) refuse('generated_js_syntax_invalid');
  let emitted_sha256 = null;
  let emitted_source = null;
  if (format === 'typescript') {
    const emitted = ts.transpileModule(rewritten, {fileName: input.file, reportDiagnostics: true,
      compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext,
        isolatedModules: true, importsNotUsedAsValues: ts.ImportsNotUsedAsValues.Remove}});
    if (diagnostics(emitted.diagnostics || []).length) refuse('trusted_typescript_emit_failed');
    emitted_source = emitted.outputText;
    emitted_sha256 = sha(emitted_source);
  }
  return {format, source_sha256: sha(input.source), generated_sha256: sha(rewritten),
    emitted_sha256, emitted_source, compiler_version: ts.version, transformed_source: rewritten,
    selected_symbol: input.symbol, original_symbol: input.original};
}

try {
  const input = JSON.parse(fs.readFileSync(0, 'utf8'));
  process.stdout.write(JSON.stringify(transform(input)) + '\n');
} catch (error) {
  process.stderr.write((error?.code || 'trusted_js_transform_failed') + '\n');
  process.exit(2);
}
