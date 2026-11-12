/**
 * Polls skip while the page is hidden (app in the background, another tab):
 * no requests, radio or battery for screens nobody is looking at. Pages
 * refresh on chirp-resume / visibilitychange instead.
 */
export const whenVisible = (fn) => () => { if (!document.hidden) fn() }
