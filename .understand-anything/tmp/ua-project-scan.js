#!/usr/bin/env node
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const projectRoot = process.argv[2];
const outputPath = process.argv[3];

function run(cmd) {
  try { return execSync(cmd, { cwd: projectRoot, encoding: 'utf8', maxBuffer: 50 * 1024 * 1024 }); }
  catch (e) { console.error(e.message); process.exit(1); }
}

// Step 1: File discovery via git ls-files
const allFiles = run('git ls-files').split('\n').filter(Boolean);

// Step 2: Exclusion filtering
const excludeDirPatterns = [
  /node_modules\//, /\.git\//, /vendor\//, /venv\//, /\.venv\//, /__pycache__\//,
  /\/dist\//, /\/build\//, /\/out\//, /\/coverage\//, /\.next\//, /\.cache\//, /\.turbo\//,
  /\/target\//, /\/obj\//, /\.idea\//, /\.vscode\//,
  /\.omc\//, /\.code-review-graph\//, /\.ruff_cache\//, /\.mypy_cache\//,
  /\.understand-anything\//, /\.sisyphus\//, /archive\//, /\.gemini\//,
  /polyedge-docs\//, /scratch\//
];
const excludeExtPatterns = [
  /\.lock$/, /package-lock\.json$/, /yarn\.lock$/, /pnpm-lock\.yaml$/,
  /\.png$/, /\.jpg$/, /\.jpeg$/, /\.gif$/, /\.svg$/, /\.ico$/,
  /\.woff$/, /\.woff2$/, /\.ttf$/, /\.eot$/,
  /\.mp3$/, /\.mp4$/, /\.pdf$/, /\.zip$/, /\.tar$/, /\.gz$/,
  /\.min\.js$/, /\.min\.css$/, /\.map$/,
  /\.db$/, /\.db-wal$/, /\.db-shm$/, /\.db-bak/,
  /\.pkl$/, /\.pkl\.json$/
];
const excludeNamePatterns = [
  /^LICENSE$/, /\.gitignore$/, /\.editorconfig$/, /\.prettierrc$/, /\.eslintrc/, /\.log$/,
  /^\.nojekyll$/
];

function shouldExclude(f) {
  // Check dir patterns
  for (const p of excludeDirPatterns) { if (p.test(f)) return true; }
  // Check ext patterns
  for (const p of excludeExtPatterns) { if (p.test(f)) return true; }
  // Check name patterns
  const basename = path.basename(f);
  for (const p of excludeNamePatterns) { if (p.test(basename)) return true; }
  return false;
}

const files = allFiles.filter(f => !shouldExclude(f));

// Step 3: Language detection
const extLangMap = {
  '.py': 'python', '.ts': 'typescript', '.tsx': 'typescript', '.js': 'javascript', '.jsx': 'javascript',
  '.md': 'markdown', '.yaml': 'yaml', '.yml': 'yaml', '.json': 'json', '.toml': 'toml',
  '.sql': 'sql', '.html': 'html', '.css': 'css', '.scss': 'scss', '.sh': 'shell', '.bash': 'shell',
  '.cfg': 'config', '.ini': 'config', '.env': 'config', '.env.example': 'config',
  '.txt': 'text', '.rst': 'rst', '.xml': 'xml',
};
const nameLangMap = {
  'Dockerfile': 'dockerfile', 'Makefile': 'makefile', 'Procfile': 'procfile',
  'Jenkinsfile': 'jenkinsfile', '.dockerignore': 'dockerfile'
};

function getLang(f) {
  const basename = path.basename(f);
  if (nameLangMap[basename]) return nameLangMap[basename];
  const ext = path.extname(f);
  if (ext === '.example' && f.endsWith('.env.example')) return 'config';
  return extLangMap[ext] || 'unknown';
}

// Step 4: File category
function getCategory(f, lang) {
  const ext = path.extname(f);
  const basename = path.basename(f);
  // docs
  if (['.md', '.rst', '.txt'].includes(ext) && basename !== 'LICENSE') return 'docs';
  // infra first (more specific than config)
  if (basename === 'Dockerfile' || basename === '.dockerignore' || basename.startsWith('docker-compose')) return 'infra';
  if (ext === '.tf' || ext === '.tfvars') return 'infra';
  if (f.includes('.github/workflows/')) return 'infra';
  if (basename === 'Procfile' || basename === 'Makefile' || basename === 'Jenkinsfile') return 'infra';
  if (ext === '.sh' || ext === '.bash') return 'script';
  // data
  if (ext === '.sql') return 'data';
  if (ext === '.csv') return 'data';
  // markup
  if (['.html', '.htm', '.css', '.scss', '.sass', '.less'].includes(ext)) return 'markup';
  // config
  if (['.yaml', '.yml', '.json', '.toml', '.xml', '.cfg', '.ini'].includes(ext)) return 'config';
  if (basename === '.env' || basename === '.env.example') return 'config';
  if (basename === 'tsconfig.json' || basename === 'package.json' || basename === 'pyproject.toml') return 'config';
  // code
  return 'code';
}

// Step 5: Line counting (batch)
let lineCounts = {};
const batchSize = 50;
for (let i = 0; i < files.length; i += batchSize) {
  const batch = files.slice(i, i + batchSize);
  try {
    const result = run(`wc -l "${batch.join('" "')}"`);
    result.split('\n').forEach(line => {
      const match = line.match(/^\s*(\d+)\s+(.+)$/);
      if (match) {
        const count = parseInt(match[1], 10);
        const filepath = match[2].replace(projectRoot + '/', '');
        lineCounts[filepath] = count;
      }
    });
  } catch (e) {
    // fallback: count individually
    batch.forEach(f => {
      try { lineCounts[f] = parseInt(run(`wc -l "${f}"`).trim().split(/\s+/)[0], 10); }
      catch { lineCounts[f] = 0; }
    });
  }
}

// Step 6: Framework detection
const frameworks = [];
const requirementsTxt = files.includes('requirements.txt') ?
  fs.readFileSync(path.join(projectRoot, 'requirements.txt'), 'utf8') : '';
const frontendPkgJson = files.includes('frontend/package.json') ?
  JSON.parse(fs.readFileSync(path.join(projectRoot, 'frontend/package.json'), 'utf8')) : null;

const pyFrameworkMap = {
  'fastapi': 'FastAPI', 'uvicorn': 'Uvicorn', 'sqlalchemy': 'SQLAlchemy',
  'alembic': 'Alembic', 'pydantic': 'Pydantic', 'apscheduler': 'APScheduler',
  'redis': 'Redis', 'httpx': 'HTTPX', 'aiohttp': 'AIOHTTP',
  'anthropic': 'Anthropic Claude', 'groq': 'Groq', 'structlog': 'Structlog',
  'slowapi': 'SlowAPI', 'pybreaker': 'PyBreaker'
};
Object.entries(pyFrameworkMap).forEach(([pkg, name]) => {
  if (requirementsTxt.toLowerCase().includes(pkg)) frameworks.push(name);
});

if (frontendPkgJson) {
  const deps = { ...frontendPkgJson.dependencies, ...frontendPkgJson.devDependencies };
  const jsFrameworkMap = {
    'react': 'React', 'typescript': 'TypeScript', 'vite': 'Vite',
    '@tanstack/react-query': 'TanStack Query', 'tailwindcss': 'Tailwind CSS',
    'vitest': 'Vitest', '@playwright/test': 'Playwright',
    'zustand': 'Zustand', 'd3': 'D3.js'
  };
  Object.entries(jsFrameworkMap).forEach(([pkg, name]) => {
    if (deps[pkg]) frameworks.push(name);
  });
}

// Infrastructure
if (files.some(f => path.basename(f) === 'Dockerfile')) frameworks.push('Docker');
if (files.some(f => path.basename(f).startsWith('docker-compose'))) frameworks.push('Docker Compose');
if (files.some(f => f.includes('.github/workflows/'))) frameworks.push('GitHub Actions');

// Step 7: Complexity
const complexity = files.length <= 30 ? 'small' : files.length <= 150 ? 'moderate' : files.length <= 500 ? 'large' : 'very-large';

// Step 8: Project name
let name = path.basename(projectRoot);
if (frontendPkgJson?.name) name = frontendPkgJson.name;

// Step 9: Import resolution (code files only)
const importMap = {};
const codeFiles = files.filter(f => getCategory(f, getLang(f)) === 'code');

// Simple import extraction for Python and TS/JS
codeFiles.forEach(f => {
  const fullPath = path.join(projectRoot, f);
  if (!fs.existsSync(fullPath)) { importMap[f] = []; return; }
  
  const content = fs.readFileSync(fullPath, 'utf8');
  const resolved = [];
  const lang = getLang(f);
  
  if (lang === 'python') {
    // Match: from .xxx import, from ..xxx import, from . import xxx
    const pyImports = content.matchAll(/from\s+((?:\.\.)+[\w.]*|\.[\w.]*)\s+import/g);
    for (const m of pyImports) {
      const importPath = m[1];
      const parts = importPath.split('.');
      let resolvedPath;
      if (importPath.startsWith('..')) {
        const parentDir = path.dirname(path.dirname(f));
        resolvedPath = path.join(parentDir, parts.slice(2).filter(Boolean).join('/'));
      } else {
        const dir = path.dirname(f);
        resolvedPath = path.join(dir, parts.slice(1).filter(Boolean).join('/'));
      }
      // Try .py and /__init__.py
      for (const candidate of [resolvedPath + '.py', path.join(resolvedPath, '__init__.py')]) {
        const normalized = candidate.replace(/\\/g, '/');
        if (files.includes(normalized)) {
          resolved.push(normalized);
          break;
        }
      }
    }
  } else if (lang === 'typescript' || lang === 'javascript') {
    // Match: import ... from './...' or './...' or '../...'
    const tsImports = content.matchAll(/(?:import\s+.*?\s+from|require)\s*\(?['"](\.[^'"]+)['"]\)?/g);
    for (const m of tsImports) {
      const importPath = m[1];
      const dir = path.dirname(f);
      let resolvedPath = path.join(dir, importPath).replace(/\\/g, '/');
      // Try extensions
      const exts = ['.ts', '.tsx', '.js', '.jsx', '/index.ts', '/index.tsx', '/index.js'];
      let found = false;
      for (const ext of exts) {
        const candidate = resolvedPath + ext;
        if (files.includes(candidate)) {
          resolved.push(candidate);
          found = true;
          break;
        }
      }
      if (!found && files.includes(resolvedPath)) {
        resolved.push(resolvedPath);
      }
    }
  }
  
  importMap[f] = [...new Set(resolved)];
});

// Non-code files get empty arrays
files.forEach(f => {
  if (!importMap.hasOwnProperty(f)) importMap[f] = [];
});

// Build file list with metadata
const fileList = files.map(f => ({
  path: f,
  language: getLang(f),
  sizeLines: lineCounts[f] || 0,
  fileCategory: getCategory(f, getLang(f))
}));

// Readme head
let readmeHead = '';
const readmePath = path.join(projectRoot, 'README.md');
if (fs.existsSync(readmePath)) {
  readmeHead = fs.readFileSync(readmePath, 'utf8').split('\n').slice(0, 10).join('\n');
}

const result = {
  scriptCompleted: true,
  name: name,
  rawDescription: frontendPkgJson?.description || '',
  readmeHead: readmeHead,
  languages: [...new Set(fileList.map(f => f.language))].filter(l => l !== 'unknown').sort(),
  frameworks: [...new Set(frameworks)].sort(),
  files: fileList,
  totalFiles: fileList.length,
  filteredByIgnore: allFiles.length - files.length,
  estimatedComplexity: complexity,
  importMap: importMap
};

fs.writeFileSync(outputPath, JSON.stringify(result, null, 2));
console.log(`Scan complete: ${files.length} files`);
