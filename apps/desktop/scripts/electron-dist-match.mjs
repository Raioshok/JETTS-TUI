import fs from 'node:fs'
import path from 'node:path'

export function electronDistVersion(dist) {
  if (!dist) return null
  try {
    return fs.readFileSync(path.join(dist, 'version'), 'utf8').trim().replace(/^v/, '')
  } catch {
    return null
  }
}

export function matchesElectronDist(dist, binary, expectedVersion) {
  return Boolean(
    dist &&
    expectedVersion &&
    fs.existsSync(binary) &&
    electronDistVersion(dist) === expectedVersion
  )
}
