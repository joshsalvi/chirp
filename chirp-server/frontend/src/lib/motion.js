// Chart animations (Recharts animates every series for about 1.5 s) cost the
// most on phones, where several charts animating at once made the
// Statistics page stutter. They run only on desktop browsers that allow motion.
import { isApp } from '../native'

const media = q => typeof window !== 'undefined' && window.matchMedia?.(q)?.matches

export const CHART_ANIMATION = !(isApp() || media('(pointer: coarse)') || media('(prefers-reduced-motion: reduce)'))
