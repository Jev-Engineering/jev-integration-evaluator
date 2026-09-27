// Parse only: never load tsconfig plugins, import target modules, emit, or execute them.
'use strict';
const fs = require('fs');
let ts;
try { ts = require('typescript'); } catch (_) {
  process.stderr.write('Install TypeScript >=5,<7 in the skill tooling directory or NODE_PATH.\n');
  process.exit(3);
}
if (Number(ts.versionMajorMinor.split('.')[0]) >= 7) process.exit(4);
const request = JSON.parse(fs.readFileSync(0, 'utf8'));
const source = ts.createSourceFile(request.file, request.source, ts.ScriptTarget.Latest, true);
const functions = [], imports = [];
const line = n => source.getLineAndCharacterOfPosition(n.getStart(source)).line + 1;
const isFn = n => ts.isFunctionDeclaration(n) || ts.isMethodDeclaration(n) || ts.isFunctionExpression(n) || ts.isArrowFunction(n);
function inspect(n, scope) {
  if (ts.isImportDeclaration(n) && n.moduleSpecifier) imports.push(n.moduleSpecifier.text);
  if (ts.isClassDeclaration(n)) scope = scope.concat(n.name ? n.name.text : '<class>');
  if (isFn(n) && n.body) {
    let name = n.name ? n.name.getText(source) : (n.parent && ts.isVariableDeclaration(n.parent) ? n.parent.name.getText(source) : '<anonymous@' + line(n) + '>');
    const symbol = scope.concat(name).join('.');
    const f = {symbol, start_line:line(n), end_line:source.getLineAndCharacterOfPosition(n.end).line+1,
      calls:[], branches:[], loops:[], exceptions:[], returns:[], literals:[], identifiers:[], attributes:[], operators:[], dataflow:[], parser:'typescript_ast'};
    const walk = x => {
      if (x !== n && isFn(x)) return;
      if (ts.isCallExpression(x) || ts.isNewExpression(x)) f.calls.push({name:x.expression.getText(source), line:line(x)});
      if (ts.isIdentifier(x)) f.identifiers.push(x.text);
      if (ts.isPropertyAccessExpression(x)) f.attributes.push(x.name.text);
      if (ts.isIfStatement(x) || ts.isConditionalExpression(x) || ts.isSwitchStatement(x)) f.branches.push(line(x));
      if (ts.isWhileStatement(x) || ts.isForStatement(x) || ts.isForOfStatement(x) || ts.isForInStatement(x) || ts.isDoStatement(x)) f.loops.push(line(x));
      if (ts.isTryStatement(x) || ts.isCatchClause(x) || ts.isThrowStatement(x)) f.exceptions.push(line(x));
      if (ts.isReturnStatement(x)) f.returns.push({line:line(x), kind:x.expression ? ts.SyntaxKind[x.expression.kind] : 'void'});
      if (ts.isStringLiteral(x) || ts.isNoSubstitutionTemplateLiteral(x)) f.literals.push({value:x.text.slice(0,2000), line:line(x)});
      if (ts.isBinaryExpression(x)) f.operators.push(ts.tokenToString(x.operatorToken.kind) || 'binary');
      if (ts.isVariableDeclaration(x) && x.initializer) {
        const callees = [], reads = [];
        const collect = z => { if (ts.isCallExpression(z)) callees.push(z.expression.getText(source)); if (ts.isIdentifier(z)) reads.push(z.text); ts.forEachChild(z, collect); };
        collect(x.initializer); f.dataflow.push({target:x.name.getText(source), calls:callees, reads, line:line(x)});
      }
      ts.forEachChild(x, walk);
    };
    walk(n); functions.push(f); scope = scope.concat(name);
  }
  ts.forEachChild(n, x => inspect(x, scope));
}
inspect(source, []);
console.log(JSON.stringify({functions, imports, version:ts.version, errors:(source.parseDiagnostics||[]).map(x => ({line:source.getLineAndCharacterOfPosition(x.start||0).line+1, message:ts.flattenDiagnosticMessageText(x.messageText,' ')}))}));
