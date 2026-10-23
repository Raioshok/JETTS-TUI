/** Human-readable names for shiki language ids, for the editor status bar. */
const LABELS: Record<string, string> = {
  bash: 'Shell',
  c: 'C',
  cpp: 'C++',
  csharp: 'C#',
  css: 'CSS',
  go: 'Go',
  html: 'HTML',
  java: 'Java',
  javascript: 'JavaScript',
  json: 'JSON',
  jsonc: 'JSON',
  jsx: 'JSX',
  kotlin: 'Kotlin',
  markdown: 'Markdown',
  php: 'PHP',
  powershell: 'PowerShell',
  python: 'Python',
  ruby: 'Ruby',
  rust: 'Rust',
  scss: 'SCSS',
  shellscript: 'Shell',
  sql: 'SQL',
  swift: 'Swift',
  text: 'Plain text',
  toml: 'TOML',
  tsx: 'TSX',
  typescript: 'TypeScript',
  xml: 'XML',
  yaml: 'YAML'
}

export function languageLabel(id: string | undefined): string {
  const key = (id || 'text').trim().toLowerCase()

  return LABELS[key] ?? key.charAt(0).toUpperCase() + key.slice(1)
}

/** Line count as an editor shows it: a trailing newline does not start a line. */
export function countLines(text: string): number {
  if (!text) {
    return 0
  }

  let lines = 1

  for (let i = text.indexOf('\n'); i !== -1; i = text.indexOf('\n', i + 1)) {
    lines += 1
  }

  return text.endsWith('\n') ? lines - 1 : lines
}
