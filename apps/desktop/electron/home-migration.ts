import fs from 'node:fs'
import path from 'node:path'

/** Match the installers: new checkouts use jettstui, existing Git checkouts keep their path. */
export function managedCheckoutRoot(home: string): string {
  const branded = path.join(home, 'jettstui')
  const legacy = path.join(home, 'freeide-agent')
  const hasGitDirectory = (root: string) => {
    try {
      return fs.statSync(path.join(root, '.git')).isDirectory()
    } catch {
      return false
    }
  }

  if (hasGitDirectory(branded)) {
    return branded
  }
  if (hasGitDirectory(legacy)) {
    return legacy
  }
  return branded
}

/** Move the default home only when the destination is absent.
 *
 * The old path becomes an alias so older managed runtimes and shortcuts keep
 * working. Explicit FREEIDE_HOME overrides never call this function.
 */
export function migrateDefaultHome(newPath: string, oldPath: string): string {
  if (fs.existsSync(newPath)) {
    return newPath
  }
  let oldStat: fs.Stats
  try {
    oldStat = fs.lstatSync(oldPath)
  } catch {
    return newPath
  }
  if (!oldStat.isDirectory() || oldStat.isSymbolicLink()) {
    return newPath
  }

  try {
    fs.renameSync(oldPath, newPath)
  } catch {
    return oldPath
  }
  try {
    fs.symlinkSync(newPath, oldPath, process.platform === 'win32' ? 'junction' : 'dir')
  } catch {
    try {
      fs.renameSync(newPath, oldPath)
      return oldPath
    } catch {
      // The moved data remains at newPath. Never overwrite a concurrent path.
      return newPath
    }
  }
  return newPath
}
