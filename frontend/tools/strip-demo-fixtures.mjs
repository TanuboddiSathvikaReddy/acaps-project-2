#!/usr/bin/env node
/**
 * Post-build step: demo fixtures (public/mock/*.json) are copied into dist/mock by Vite like any
 * other public/ asset. They must not ship in a production build unless the build was explicitly
 * made for demo use (VITE_DEMO_MODE=true at build time). This removes dist/mock in that case, so
 * the ~45 MB of fixtures and their contents never reach a real deployment by default.
 */
import { rm, access } from 'node:fs/promises'
import path from 'node:path'

const demo = (process.env.VITE_DEMO_MODE ?? '') === 'true'
const dir = path.join(process.cwd(), 'dist', 'mock')

if (demo) {
  console.log('[strip-demo-fixtures] VITE_DEMO_MODE=true: keeping dist/mock for this build.')
} else {
  try {
    await access(dir)
    await rm(dir, { recursive: true, force: true })
    console.log('[strip-demo-fixtures] Removed dist/mock (demo mode is off for this build).')
  } catch {
    console.log('[strip-demo-fixtures] dist/mock not present, nothing to remove.')
  }
}
