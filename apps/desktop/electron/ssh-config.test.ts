import assert from 'node:assert/strict'
import os from 'node:os'
import path from 'node:path'

import { test } from 'vitest'

import { collectSshConfigHosts, parseSshConfigHosts, parseSshConfigIncludes, parseSshGOutput } from './ssh-config'

test('parseSshConfigHosts keeps literal aliases and drops wildcard/negated patterns', () => {
  const cfg = [
    'Host devbox',
    '  HostName 10.0.0.5',
    'Host *.internal prod !staging glob*',
    'Host alpha beta',
    '# Host commented-out',
    'host lower-case'
  ].join('\n')

  assert.deepEqual(parseSshConfigHosts(cfg), ['devbox', 'prod', 'alpha', 'beta', 'lower-case'])
})

test('parseSshConfigHosts de-duplicates', () => {
  assert.deepEqual(parseSshConfigHosts('Host box\nHost box\nHost box other'), ['box', 'other'])
})

test('parseSshConfigIncludes extracts include tokens', () => {
  const cfg = 'Include ~/.ssh/config.d/*\nInclude work_hosts personal_hosts\n# Include ignored'
  assert.deepEqual(parseSshConfigIncludes(cfg), ['~/.ssh/config.d/*', 'work_hosts', 'personal_hosts'])
})

test('collectSshConfigHosts follows Include directives (read-only)', () => {
  const home = path.join(os.tmpdir(), 'ssh-config-test-home')
  const sshDir = path.join(home, '.ssh')
  const config = path.join(sshDir, 'config')
  const files = {
    [config]: 'Host main\nInclude work\nInclude ~/abs_inc',
    [path.join(sshDir, 'work')]: 'Host work-box\nInclude nested',
    [path.join(sshDir, 'nested')]: 'Host deep',
    [path.join(home, 'abs_inc')]: 'Host home-abs'
  }

  const hosts = collectSshConfigHosts(config, {
    homeDir: home,
    readFile: p => files[p] ?? null
  })

  assert.deepEqual(hosts.sort(), ['deep', 'home-abs', 'main', 'work-box'].sort())
})

test('collectSshConfigHosts tolerates a missing config file', () => {
  assert.deepEqual(collectSshConfigHosts('/nope/config', { homeDir: '/home/u', readFile: () => null }), [])
})

test('collectSshConfigHosts does not loop on a self-include cycle', () => {
  const home = path.join(os.tmpdir(), 'ssh-config-test-home')
  const sshDir = path.join(home, '.ssh')
  const config = path.join(sshDir, 'config')
  const files = {
    [config]: 'Host a\nInclude loop',
    [path.join(sshDir, 'loop')]: 'Host b\nInclude config' // points back at config
  }

  const hosts = collectSshConfigHosts(config, {
    homeDir: home,
    readFile: p => files[p] ?? null
  })

  assert.deepEqual(hosts.sort(), ['a', 'b'])
})

test('collectSshConfigHosts expands globbed includes via injected globSync', () => {
  const home = path.join(os.tmpdir(), 'ssh-config-test-home')
  const sshDir = path.join(home, '.ssh')
  const config = path.join(sshDir, 'config')
  const work = path.join(sshDir, 'config.d', '10-work')
  const personal = path.join(sshDir, 'config.d', '20-home')
  const files = {
    [config]: 'Host root\nInclude config.d/*',
    [work]: 'Host work',
    [personal]: 'Host home'
  }

  const hosts = collectSshConfigHosts(config, {
    homeDir: home,
    readFile: p => files[p] ?? null,
    globSync: pattern =>
      path.basename(pattern) === '*' ? [work, personal] : [pattern]
  })

  assert.deepEqual(hosts.sort(), ['home', 'root', 'work'].sort())
})

test('parseSshGOutput pulls hostname/user/port/identityfile', () => {
  const out = [
    'host devbox',
    'hostname 10.0.0.5',
    'user alice',
    'port 2222',
    'identityfile ~/.ssh/id_ed25519',
    'forwardagent no'
  ].join('\n')

  assert.deepEqual(parseSshGOutput(out), {
    hostname: '10.0.0.5',
    user: 'alice',
    port: 2222,
    identityFile: '~/.ssh/id_ed25519'
  })
})

test('parseSshGOutput takes the FIRST identityfile and tolerates missing keys', () => {
  const out = 'hostname box\nidentityfile ~/.ssh/a\nidentityfile ~/.ssh/b'
  const parsed = parseSshGOutput(out)
  assert.equal(parsed.identityFile, '~/.ssh/a')
  assert.equal(parsed.user, null)
  assert.equal(parsed.port, null)
})
