// Read-only, finite terminal workload for the interactive TUI smoke test.
// Run from the repository root: !node ui-tui/scripts/tui-busy-smoke.mjs
const total = 20
let elapsed = 0

console.log('busy smoke started')

const timer = setInterval(() => {
  elapsed += 1
  console.log(`busy smoke ${elapsed}/${total}`)

  if (elapsed >= total) {
    clearInterval(timer)
    console.log('busy smoke complete')
  }
}, 1000)
