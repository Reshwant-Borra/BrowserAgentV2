import { CONTROL_CLIENT_SCRIPT } from "./controlChannel.js";

function page(title: string, body: string, extraHead = ""): string {
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>${title}</title>
${extraHead}
<style>
  body { font-family: system-ui, sans-serif; margin: 24px; max-width: 720px; }
  button, input, textarea { font-size: 14px; padding: 6px; margin: 4px 0; }
  .row { margin-bottom: 16px; }
  [data-testid] { border: 1px dashed #ccc; padding: 8px; }
  #nav { font-size: 12px; margin-bottom: 24px; }
  #nav a { margin-right: 8px; }
</style>
</head>
<body>
<div id="nav"><a href="/">index</a></div>
${body}
<script>${CONTROL_CLIENT_SCRIPT}</script>
</body>
</html>`;
}

export function indexPage(): string {
  const links = [
    ["a", "Normal typing"],
    ["b", "Controlled/rerendering input"],
    ["c", "Delayed hydration"],
    ["d", "Stale targets"],
    ["e", "Popups/tabs"],
    ["f", "Frames"],
    ["g", "Dialogs"],
    ["h", "Persistence"],
    ["i", "Human handoff"],
    ["j", "Downloads"],
    ["l", "Tab/page ownership"],
  ]
    .map(([slug, label]) => `<li><a href="/fixtures/${slug}">${label}</a></li>`)
    .join("\n");
  return page("BrowserKernel Fixtures", `<h1>BrowserKernel Fixtures</h1><ul>${links}</ul>`);
}

// ---------------------------------------------------------------------------
// Fixture A — normal typing
// ---------------------------------------------------------------------------
export function fixtureA(): string {
  return page(
    "Fixture A - Normal typing",
    `
<h1>Fixture A — Normal typing</h1>
<div class="row">
  <label>Plain input<br><input id="plain-input" type="text"></label>
</div>
<div class="row">
  <label>Textarea<br><textarea id="plain-textarea" rows="3"></textarea></label>
</div>
<div class="row">
  <label>Prefilled (clear + replace)<br><input id="prefilled-input" type="text" value="old-value-123"></label>
</div>
<div class="row">
  <label>Special chars<br><input id="special-chars-input" type="text"></label>
</div>
<form id="search-form" class="row">
  <label>Search (Enter to submit)<br><input id="search-input" type="text" name="q"></label>
  <div id="search-result" data-testid="search-result"></div>
</form>
<script>
document.getElementById('search-form').addEventListener('submit', function (e) {
  e.preventDefault();
  var v = document.getElementById('search-input').value;
  document.getElementById('search-result').textContent = 'submitted:' + v;
});
</script>
`
  );
}

// ---------------------------------------------------------------------------
// Fixture B — controlled/rerendering input
// ---------------------------------------------------------------------------
export function fixtureB(): string {
  return page(
    "Fixture B - Controlled input",
    `
<h1>Fixture B — Controlled/rerendering input</h1>
<p>Simulates a React-style controlled component that replaces its own DOM node
on every re-render (new element identity each keystroke), while carrying
forward the committed value.</p>
<div id="controlled-container" class="row"></div>
<div id="controlled-render-count" data-testid="render-count">renders:0</div>
<script>
(function () {
  var container = document.getElementById('controlled-container');
  var countEl = document.getElementById('controlled-render-count');
  var state = { value: '' };
  var renders = 0;

  function render() {
    renders++;
    countEl.textContent = 'renders:' + renders;
    var input = document.createElement('input');
    input.type = 'text';
    input.id = 'controlled-input';
    input.value = state.value;
    input.addEventListener('input', function (e) {
      state.value = e.target.value;
      // Simulate React committing a re-render on next microtask, which
      // replaces the DOM node (new identity) even though the accessible
      // name/id/role stay the same.
      queueMicrotask(render);
    });
    container.replaceChildren(input);
  }
  render();
})();
</script>
`
  );
}

// ---------------------------------------------------------------------------
// Fixture C — delayed hydration
// ---------------------------------------------------------------------------
export function fixtureC(): string {
  return page(
    "Fixture C - Delayed hydration",
    `
<h1>Fixture C — Delayed hydration</h1>
<div id="hydration-status" data-testid="hydration-status">not-hydrated</div>
<div id="hydrate-container" class="row">
  <input id="hydrate-input" type="text" value="">
</div>
<script>
(function () {
  var delayMs = 900 + Math.floor(Math.random() * 400);
  setTimeout(function () {
    var container = document.getElementById('hydrate-container');
    var fresh = document.createElement('input');
    fresh.type = 'text';
    fresh.id = 'hydrate-input';
    fresh.value = '';
    container.replaceChildren(fresh);
    document.getElementById('hydration-status').textContent = 'hydrated';
    document.getElementById('hydration-status').setAttribute('data-hydrated', 'true');
    window.__HYDRATED__ = true;
  }, delayMs);
})();
</script>
`
  );
}

// ---------------------------------------------------------------------------
// Fixture D — stale targets
// ---------------------------------------------------------------------------
export function fixtureD(): string {
  return page(
    "Fixture D - Stale targets",
    `
<h1>Fixture D — Stale targets</h1>
<div class="row">
  <button id="target-btn">Click Me A</button>
  <span id="click-log" data-testid="click-log">no-clicks</span>
</div>
<div class="row">
  <ul id="dom-list">
    <li id="item-1" role="button" tabindex="0">Item One</li>
    <li id="item-2" role="button" tabindex="0">Item Two</li>
  </ul>
</div>
<div id="spa-content" class="row" data-testid="spa-content">
  <button id="spa-btn-home">SPA Home Button</button>
</div>
<script>
document.getElementById('target-btn').addEventListener('click', function () {
  document.getElementById('click-log').textContent = 'clicked:' + this.dataset.gen;
});
document.getElementById('target-btn').dataset.gen = '0';

window.addEventListener('bk:stale_rerender', function () {
  var old = document.getElementById('target-btn');
  var fresh = document.createElement('button');
  fresh.id = 'target-btn';
  fresh.textContent = 'Click Me A';
  fresh.dataset.gen = String(Number(old.dataset.gen) + 1);
  fresh.addEventListener('click', function () {
    document.getElementById('click-log').textContent = 'clicked:' + this.dataset.gen;
  });
  old.replaceWith(fresh);
});

window.addEventListener('bk:stale_domreplace', function () {
  var list = document.getElementById('dom-list');
  list.innerHTML = '<li id="item-1" role="button" tabindex="0">Item One</li><li id="item-2" role="button" tabindex="0">Item Two</li>';
});

window.addEventListener('bk:stale_spa', function () {
  var el = document.getElementById('spa-content');
  el.innerHTML = '<button id="spa-btn-away">SPA Away Button</button>';
  history.pushState({}, '', '/fixtures/d?route=away');
});

window.addEventListener('bk:stale_navigate', function () {
  location.href = '/fixtures/a';
});
</script>
`
  );
}

// ---------------------------------------------------------------------------
// Fixture E — popups/tabs
// ---------------------------------------------------------------------------
export function fixtureE(): string {
  return page(
    "Fixture E - Popups",
    `
<h1>Fixture E — Popups/tabs</h1>
<div class="row"><a id="blank-link" href="/fixtures/a" target="_blank">target=_blank link</a></div>
<div class="row"><button id="window-open-btn" onclick="window.open('/fixtures/a?via=windowopen','_blank')">window.open</button></div>
<div class="row"><button id="delayed-popup-btn">Delayed popup (800ms)</button></div>
<div class="row"><button id="popup-from-popup-btn" onclick="window.open('/fixtures/e/child','_blank')">Open popup with its own nested-popup button</button></div>
<script>
document.getElementById('delayed-popup-btn').addEventListener('click', function () {
  setTimeout(function () { window.open('/fixtures/a?via=delayed', '_blank'); }, 800);
});
window.addEventListener('bk:external_open_tab', function () {
  window.open('/fixtures/a?via=external', '_blank');
});
</script>
`
  );
}

export function fixtureEChild(): string {
  return page(
    "Fixture E - Popup child",
    `
<h1>Popup child page</h1>
<button id="nested-popup-btn" onclick="window.open('/fixtures/a?via=nested','_blank')">Open nested popup</button>
`
  );
}

// ---------------------------------------------------------------------------
// Fixture F — frames
// ---------------------------------------------------------------------------
export function fixtureF(): string {
  return page(
    "Fixture F - Frames",
    `
<h1>Fixture F — Frames</h1>
<div class="row">
  <iframe id="frame1" src="/fixtures/f/inner?label=A" width="400" height="160"></iframe>
</div>
<div class="row">
  <button id="replace-frame-btn">(auto via control event bk:replace_frame)</button>
</div>
<div class="row">
  <iframe id="frame-nested-outer" src="/fixtures/f/inner?label=Outer&nested=1" width="420" height="260"></iframe>
</div>
<script>
window.addEventListener('bk:replace_frame', function () {
  var f = document.getElementById('frame1');
  f.src = '/fixtures/f/inner?label=B';
});
</script>
`
  );
}

export function fixtureFInner(label: string, nested: boolean): string {
  return `<!doctype html>
<html><head><meta charset="utf-8"><title>Frame ${label}</title></head>
<body style="font-family:system-ui;margin:12px;">
<div data-testid="frame-label">frame-${label}</div>
<button id="frame-btn-${label}">Frame Button ${label}</button>
<input id="frame-input-${label}" type="text">
${nested ? `<iframe id="frame-nested-inner" src="/fixtures/f/inner?label=Nested" width="360" height="140"></iframe>` : ""}
</body></html>`;
}

// ---------------------------------------------------------------------------
// Fixture G — dialogs
// ---------------------------------------------------------------------------
export function fixtureG(): string {
  return page(
    "Fixture G - Dialogs",
    `
<h1>Fixture G — Dialogs</h1>
<div class="row">
  <button id="alert-btn">Alert</button>
  <span id="alert-result" data-testid="alert-result">none</span>
</div>
<div class="row">
  <button id="confirm-btn">Confirm</button>
  <span id="confirm-result" data-testid="confirm-result">none</span>
</div>
<div class="row">
  <button id="prompt-btn">Prompt</button>
  <span id="prompt-result" data-testid="prompt-result">none</span>
</div>
<script>
document.getElementById('alert-btn').addEventListener('click', function () {
  alert('Hello from alert');
  document.getElementById('alert-result').textContent = 'dismissed';
});
document.getElementById('confirm-btn').addEventListener('click', function () {
  var ok = confirm('Are you sure?');
  document.getElementById('confirm-result').textContent = ok ? 'accepted' : 'dismissed';
});
document.getElementById('prompt-btn').addEventListener('click', function () {
  var v = prompt('Enter value', 'default-value');
  document.getElementById('prompt-result').textContent = (v === null) ? 'null' : ('value:' + v);
});
</script>
`
  );
}

// ---------------------------------------------------------------------------
// Fixture H — persistence
// ---------------------------------------------------------------------------
export function fixtureH(seed: boolean): string {
  return page(
    "Fixture H - Persistence",
    `
<h1>Fixture H — Persistence</h1>
<div id="persist-status" data-testid="persist-status">unknown</div>
<script>
${
  seed
    ? `document.cookie = 'bk_session=abc123; path=/; max-age=86400'; localStorage.setItem('bk_local', 'xyz789'); localStorage.setItem('bk_auth', 'logged_in');`
    : ""
}
document.getElementById('persist-status').textContent =
  'cookie:' + (document.cookie.includes('bk_session=abc123') ? 'present' : 'absent') +
  ' local:' + (localStorage.getItem('bk_local') || 'absent') +
  ' auth:' + (localStorage.getItem('bk_auth') || 'absent');
</script>
`
  );
}

// ---------------------------------------------------------------------------
// Fixture I — human handoff
// ---------------------------------------------------------------------------
export function fixtureI(): string {
  return page(
    "Fixture I - Human handoff",
    `
<h1>Fixture I — Human handoff (fake login/MFA)</h1>
<div id="handoff-status" data-testid="handoff-status">AWAITING_LOGIN</div>
<div id="login-form" class="row">
  <label>Username<br><input id="username" type="text"></label><br>
  <label>Password<br><input id="password" type="password"></label><br>
  <button id="login-btn" disabled>Log in (enabled only by real human click)</button>
</div>
<script>
document.getElementById('username').addEventListener('input', check);
document.getElementById('password').addEventListener('input', check);
function check() {
  var ok = document.getElementById('username').value.length > 0 &&
           document.getElementById('password').value.length > 0;
  document.getElementById('login-btn').disabled = !ok;
}
document.getElementById('login-btn').addEventListener('click', function () {
  document.getElementById('handoff-status').textContent = 'LOGIN_CLICKED_BY_HUMAN';
});

window.addEventListener('bk:complete_login', function (e) {
  document.getElementById('handoff-status').textContent = 'LOGGED_IN';
  var main = document.body;
  var dashboard = document.createElement('div');
  dashboard.id = 'dashboard';
  dashboard.innerHTML = '<h2>Dashboard</h2><div data-testid="dashboard-marker">post-login-content</div><button id="dashboard-btn">Dashboard Button</button>';
  document.getElementById('login-form').replaceWith(dashboard);
  if (e.detail && e.detail.openPopup) {
    window.open('/fixtures/i/dashboard-popup', '_blank');
  }
});

window.addEventListener('bk:complete_login_navigate', function () {
  location.href = '/fixtures/i/dashboard';
});
</script>
`
  );
}

export function fixtureIDashboard(): string {
  return page(
    "Fixture I - Dashboard",
    `<h1>Dashboard (post-navigation)</h1><div data-testid="dashboard-marker">post-login-content</div><button id="dashboard-btn">Dashboard Button</button>`
  );
}

export function fixtureIDashboardPopup(): string {
  return page("Fixture I - Welcome popup", `<h1>Welcome</h1><div data-testid="popup-marker">welcome-popup</div>`);
}

// ---------------------------------------------------------------------------
// Fixture J — downloads
// ---------------------------------------------------------------------------
export function fixtureJ(): string {
  return page(
    "Fixture J - Downloads",
    `
<h1>Fixture J — Downloads</h1>
<div class="row"><a id="download-link" href="/fixtures/j/file?name=report.txt&size=2048" download="report.txt">Download report.txt</a></div>
<div class="row"><a id="download-slow-link" href="/fixtures/j/file?name=slow.bin&size=500000&delayMs=400" download="slow.bin">Download slow.bin</a></div>
<div class="row"><a id="download-fail-link" href="/fixtures/j/fail?name=broken.bin" download="broken.bin">Download broken.bin (fails)</a></div>
`
  );
}

// ---------------------------------------------------------------------------
// Fixture L — ownership
// ---------------------------------------------------------------------------
export function fixtureL(): string {
  return page(
    "Fixture L - Ownership",
    `
<h1>Fixture L — Tab/page ownership</h1>
<div class="row"><a id="agent-open-tab-link" href="/fixtures/a?via=agent-owned" target="_blank">Agent-triggered new tab</a></div>
<script>
window.addEventListener('bk:external_open_tab', function () {
  window.open('/fixtures/a?via=external-owner', '_blank');
});
</script>
`
  );
}
