/*
 * nav.js
 *
 * Renders the navigation sidebar and header actions.
 */

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', path: '/admin' },
  { id: 'users', label: 'Users', path: '/admin/users' },
  { id: 'sessions', label: 'Sessions', path: '/admin/sessions' },
  { id: 'connections', label: 'Connections', path: '/admin/connections' },
  { id: 'locations', label: 'Locations', path: '/admin/locations' },
  { id: 'chat', label: 'Chat', path: '/admin/chat' },
  { id: 'tables', label: 'Tables', path: '/admin/tables' },
  { id: 'worlds', label: 'Worlds', path: '/admin/worlds' },
];

const SUPERUSER_ITEMS = [
  { id: 'superuser', label: 'Superuser', path: '/admin/superuser' },
];

function buildNavLinks(items, activePath) {
  return items
    .map((item) => {
      const isActive = activePath === item.path;
      return `
        <a class="nav-link${isActive ? ' is-active' : ''}" href="${item.path}">
          ${item.label}
        </a>
      `;
    })
    .join('');
}

function renderNav({ root, activePath, role }) {
  const nav = root.querySelector('[data-nav]');
  if (!nav) {
    return;
  }

  const items = [...NAV_ITEMS];
  if (role === 'superuser') {
    items.push(...SUPERUSER_ITEMS);
  }

  nav.innerHTML = `
    <div class="nav-section">
      ${buildNavLinks(items, activePath)}
    </div>
  `;
}

export { renderNav };
