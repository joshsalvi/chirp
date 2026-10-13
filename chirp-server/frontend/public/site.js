// Shared by about.html and support.html.
// Once the iPhone app is approved, set its App Store link here, e.g.
// 'https://apps.apple.com/app/id6820995435' — App Store buttons then appear
// and the "coming soon" notes disappear.
var CHIRP_APP_STORE_URL = ''

document.addEventListener('DOMContentLoaded', function () {
  var live = !!CHIRP_APP_STORE_URL
  document.querySelectorAll('[data-appstore]').forEach(function (a) {
    if (live) { a.href = CHIRP_APP_STORE_URL; a.hidden = false } else a.hidden = true
  })
  document.querySelectorAll('[data-appstore-soon]').forEach(function (el) { el.hidden = live })
})
