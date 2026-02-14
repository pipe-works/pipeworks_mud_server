/*
 * nav.js
 *
 * Renders the navigation sidebar and header actions.
 */

const NAV_GROUPS = [
  {
    title: 'Overview',
    items: [
      { id: 'dashboard', label: 'Dashboard', path: '/admin' },
    ],
  },
  {
    title: 'Operations',
    items: [
      { id: 'users', label: 'Users', path: '/admin/users' },
      { id: 'sessions', label: 'Sessions', path: '/admin/sessions' },
      { id: 'connections', label: 'Connections', path: '/admin/connections' },
      { id: 'locations', label: 'Locations', path: '/admin/locations' },
      { id: 'chat', label: 'Chat', path: '/admin/chat' },
    ],
  },
  {
    title: 'Data',
    items: [
      { id: 'tables', label: 'Tables', path: '/admin/tables' },
      { id: 'schema', label: 'Schema', path: '/admin/schema' },
      { id: 'worlds', label: 'Worlds', path: '/admin/worlds' },
    ],
  },
];

const SUPERUSER_GROUP = {
  title: 'Superuser',
  items: [{ id: 'superuser', label: 'Controls', path: '/admin/superuser' }],
};

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

  const groups = [...NAV_GROUPS];
  if (role === 'superuser') {
    groups.push(SUPERUSER_GROUP);
  }

  nav.innerHTML = groups
    .map(
      (group) => `
        <div class="nav-group">
          <div class="nav-group-title">${group.title}</div>
          ${buildNavLinks(group.items, activePath)}
        </div>
      `
    )
    .join('');
}

export { renderNav };
