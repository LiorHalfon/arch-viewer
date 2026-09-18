// archview: what the TypeScript compiler knows about a project's imports (ADR 0010).
//
//   node typescript.mjs <repo> <tsconfig>
//
// Loads the analysed repo's own `typescript` package, reads the tsconfig (following
// `extends` and `references`) and prints {"files": [...]} as JSON; the format is
// documented on `read_facts` in typescript.py, which builds the model from it. The
// source is parsed, never executed. Any problem is one line on stderr and exit code 2.

import fs from "node:fs";
import path from "node:path";
import { builtinModules, createRequire } from "node:module";

const CODE = /\.(ts|tsx|mts|cts|js|jsx|mjs|cjs)$/;
const DECLARATION = /\.d\.(ts|mts|cts)$/;
const NO_INPUTS = 18003; // a solution-style tsconfig lists no files of its own
const STATEMENT = 200; // the evidence line in `check`, `why` and the viewer; never a whole file

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exit(2);
}

// An unreadable file or a throw out of the compiler is a failure like any other: one
// line, exit 2 - never a stack trace for read_facts to hand to the user.
process.on("uncaughtException", (error) => fail(error.message));

const [repoArg, tsconfigArg] = process.argv.slice(2);
if (!repoArg || !tsconfigArg) fail("usage: node typescript.mjs <repo> <tsconfig>");
if (!fs.existsSync(repoArg)) fail(`no such directory: ${repoArg}`);
const repo = fs.realpathSync(path.resolve(repoArg));
const rel = (file) => path.relative(repo, file).split(path.sep).join("/");
const real = (file) => {
  try {
    return fs.realpathSync(file);
  } catch {
    return file;
  }
};

function loadTypeScript() {
  try {
    return createRequire(path.join(repo, "package.json"))("typescript");
  } catch {
    return fail(`typescript not found in ${path.join(repo, "node_modules")}; run npm install`);
  }
}

const ts = loadTypeScript();
const message = (diagnostic) => ts.flattenDiagnosticMessageText(diagnostic.messageText, " ");

function parseConfig(configPath) {
  const host = {
    ...ts.sys,
    onUnRecoverableConfigFileDiagnostic: (d) => fail(`${rel(configPath)}: ${message(d)}`),
  };
  const parsed = ts.getParsedCommandLineOfConfigFile(configPath, {}, host);
  const errors = parsed.errors.filter(
    (d) => d.category === ts.DiagnosticCategory.Error && d.code !== NO_INPUTS,
  );
  if (errors.length > 0) fail(`${rel(configPath)}: ${message(errors[0])}`);
  return parsed;
}

function projects(configPath, found = new Map()) {
  if (found.has(configPath)) return found;
  const parsed = parseConfig(configPath);
  found.set(configPath, parsed);
  for (const reference of parsed.projectReferences ?? []) {
    projects(real(ts.resolveProjectReferencePath(reference)), found);
  }
  return found;
}

function aliasInsideRepo(specifier, options) {
  const base = options.baseUrl ?? options.pathsBasePath ?? repo;
  for (const [pattern, targets] of Object.entries(options.paths ?? {})) {
    const star = pattern.indexOf("*");
    const prefix = star < 0 ? pattern : pattern.slice(0, star);
    const suffix = star < 0 ? "" : pattern.slice(star + 1);
    const matched =
      star < 0
        ? specifier === pattern
        : specifier.length >= prefix.length + suffix.length &&
          specifier.startsWith(prefix) &&
          specifier.endsWith(suffix);
    if (!matched) continue;
    const middle = star < 0 ? "" : specifier.slice(prefix.length, specifier.length - suffix.length);
    return targets.some((target) => {
      const where = rel(path.resolve(base, target.replace("*", middle)));
      return !where.startsWith("..") && !where.split("/").includes("node_modules");
    });
  }
  return false;
}

function resolver(options) {
  const cache = ts.createModuleResolutionCache(repo, (name) => name, options);
  return (specifier, containingFile, mode) => {
    const found = ts.resolveModuleName(
      specifier, containingFile, options, ts.sys, cache, undefined, mode,
    ).resolvedModule;
    return found ? rel(real(found.resolvedFileName)) : null;
  };
}

const hasModifier = (node, kind) => (node.modifiers ?? []).some((m) => m.kind === kind);

function isImportCall(node) {
  return (
    ts.isCallExpression(node) &&
    (node.expression.kind === ts.SyntaxKind.ImportKeyword ||
      (ts.isIdentifier(node.expression) && node.expression.text === "require"))
  );
}

function allTypeOnly(clause) {
  if (!clause) return false;
  if (clause.isTypeOnly) return true;
  const named = clause.namedBindings;
  return (
    !clause.name &&
    !!named &&
    ts.isNamedImports(named) &&
    named.elements.length > 0 &&
    named.elements.every((element) => element.isTypeOnly)
  );
}

// The whole statement on one line: a wrapped `import {\n  one,\n  two,\n} from "./b";`
// reads as `import { one, two } from "./b";`, truncated so one pathological statement
// cannot bloat the JSON.
function statementText(node, source) {
  const text = source.text.slice(node.getStart(source), node.end).replace(/\s+/g, " ").trim();
  return text.length > STATEMENT ? `${text.slice(0, STATEMENT - 1)}…` : text;
}

function scan(file, options, resolve) {
  const text = fs.readFileSync(file, "utf8");
  const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true);
  const imports = [];
  const exported = { types: false, values: false };
  let abstractClass = false;

  const add = (node, literal, typeOnly, lazy) => {
    const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
    const common = { line, text: statementText(node, source), type_only: typeOnly, lazy };
    if (!literal) {
      imports.push({ specifier: null, resolved: null, ...common, dynamic: true, builtin: false, alias: false });
      return;
    }
    const specifier = literal.text;
    const mode = ts.getModeForUsageLocation?.(source, literal, options);
    const resolved = resolve(specifier, file, mode);
    const builtin =
      specifier.startsWith("node:") || (!resolved && builtinModules.includes(specifier.split("/")[0]));
    const alias = !resolved && aliasInsideRepo(specifier, options);
    imports.push({ specifier, resolved, ...common, dynamic: false, builtin, alias });
  };

  const visit = (node, inFunction) => {
    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
      add(node, node.moduleSpecifier, allTypeOnly(node.importClause), false);
    } else if (ts.isExportDeclaration(node)) {
      if (node.moduleSpecifier && ts.isStringLiteral(node.moduleSpecifier)) {
        add(node, node.moduleSpecifier, node.isTypeOnly, false);
      }
      exported[node.isTypeOnly ? "types" : "values"] = true;
    } else if (ts.isImportEqualsDeclaration(node) && ts.isExternalModuleReference(node.moduleReference)) {
      const expression = node.moduleReference.expression;
      add(node, ts.isStringLiteral(expression) ? expression : null, node.isTypeOnly, inFunction);
    } else if (isImportCall(node)) {
      const [argument] = node.arguments;
      const literal = argument && ts.isStringLiteralLike(argument) ? argument : null;
      add(node, literal, false, node.expression.kind === ts.SyntaxKind.ImportKeyword || inFunction);
    } else if (ts.isExportAssignment(node)) {
      exported.values = true;
    }
    if (ts.isClassDeclaration(node) && hasModifier(node, ts.SyntaxKind.AbstractKeyword)) {
      abstractClass = true;
    }
    if (node.parent === source && hasModifier(node, ts.SyntaxKind.ExportKeyword)) {
      const typeOnly = ts.isInterfaceDeclaration(node) || ts.isTypeAliasDeclaration(node);
      exported[typeOnly ? "types" : "values"] = true;
    }
    const nested = inFunction || ts.isFunctionLike(node);
    ts.forEachChild(node, (child) => visit(child, nested));
  };
  ts.forEachChild(source, (child) => visit(child, false));

  return { file: rel(file), abstract: abstractClass || (exported.types && !exported.values), imports };
}

const configPath = path.resolve(tsconfigArg);
if (!fs.existsSync(configPath)) fail(`no ${rel(configPath)} in ${repo}`);

const owners = new Map(); // file -> the compiler options of the first tsconfig listing it
for (const parsed of projects(real(configPath)).values()) {
  for (const name of parsed.fileNames) {
    const file = real(name);
    // A `references` entry can point at a sibling package (`{"path": "../core"}`); its
    // files are outside the repo, and an import of one is an external, not a module.
    const outside = rel(file).startsWith("../");
    const skipped =
      outside ||
      !CODE.test(file) ||
      DECLARATION.test(file) ||
      file.split(path.sep).includes("node_modules");
    if (!skipped && !owners.has(file)) owners.set(file, parsed.options);
  }
}

const resolvers = new Map();
const files = [...owners.keys()]
  .sort((a, b) => (rel(a) < rel(b) ? -1 : rel(a) > rel(b) ? 1 : 0))
  .map((file) => {
    const options = owners.get(file);
    if (!resolvers.has(options)) resolvers.set(options, resolver(options));
    return scan(file, options, resolvers.get(options));
  });
process.stdout.write(`${JSON.stringify({ files })}\n`);
