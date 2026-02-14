/*
 * schema.js
 *
 * Admin schema view. Shows database relationships as a list and SVG map.
 */

import { showToast } from '../ui/toasts.js';

/**
 * Render a human-readable list of foreign key relationships.
 */
function buildRelationsList(tables) {
  const relations = [];
  tables.forEach((table) => {
    (table.foreign_keys || []).forEach((fk) => {
      relations.push({
        source: `${table.name}.${fk.from_column}`,
        target: `${fk.ref_table}.${fk.ref_column}`,
        onDelete: fk.on_delete,
        onUpdate: fk.on_update,
      });
    });
  });

  if (!relations.length) {
    return '<p class="muted">No foreign keys found.</p>';
  }

  return `
    <ul class="schema-relations">
      ${relations
        .map(
          (rel) => `
        <li>
          <div class="relation-main">
            <span class="relation-source">${rel.source}</span>
            <span class="relation-arrow">-></span>
            <span class="relation-target">${rel.target}</span>
          </div>
          <div class="relation-meta">ON DELETE ${rel.onDelete} · ON UPDATE ${rel.onUpdate}</div>
        </li>
      `
        )
        .join('')}
    </ul>
  `;
}

/**
 * Build an SVG-based schema map using a simple grid layout.
 */
function buildSchemaMap(tables) {
  if (!tables.length) {
    return '<p class="muted">No tables found.</p>';
  }

  const cols = 2;
  const nodeWidth = 260;
  const nodeHeight = 64;
  const colGap = 140;
  const rowGap = 120;
  const paddingX = 40;
  const paddingY = 40;

  const rows = Math.ceil(tables.length / cols);
  const width = paddingX * 2 + cols * nodeWidth + (cols - 1) * colGap;
  const height = paddingY * 2 + rows * rowGap;

  const positions = new Map();
  tables.forEach((table, idx) => {
    const col = idx % cols;
    const row = Math.floor(idx / cols);
    const x = paddingX + col * (nodeWidth + colGap);
    const y = paddingY + row * rowGap;
    positions.set(table.name, { x, y });
  });

  const links = [];
  tables.forEach((table) => {
    (table.foreign_keys || []).forEach((fk) => {
      const from = positions.get(table.name);
      const to = positions.get(fk.ref_table);
      if (!from || !to) {
        return;
      }
      const sx = from.x + nodeWidth;
      const sy = from.y + nodeHeight / 2;
      const tx = to.x;
      const ty = to.y + nodeHeight / 2;
      links.push({ sx, sy, tx, ty });
    });
  });

  const linkPaths = links
    .map((link) => {
      const mx = (link.sx + link.tx) / 2;
      return `<path class="schema-link" d="M ${link.sx} ${link.sy} C ${mx} ${link.sy}, ${mx} ${link.ty}, ${link.tx} ${link.ty}" />`;
    })
    .join('');

  const nodes = tables
    .map((table) => {
      const pos = positions.get(table.name);
      if (!pos) {
        return '';
      }
      const titleX = pos.x + 16;
      const titleY = pos.y + 26;
      const metaY = pos.y + 46;
      const columnCount = table.columns ? table.columns.length : 0;
      return `
        <g class="schema-node">
          <rect x="${pos.x}" y="${pos.y}" width="${nodeWidth}" height="${nodeHeight}" rx="12" />
          <text class="schema-node-title" x="${titleX}" y="${titleY}">${table.name}</text>
          <text class="schema-node-meta" x="${titleX}" y="${metaY}">${columnCount} columns</text>
        </g>
      `;
    })
    .join('');

  return `
    <div class="schema-map">
      <svg class="schema-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Database schema map">
        ${linkPaths}
        ${nodes}
      </svg>
    </div>
  `;
}

/**
 * Render schema view into the main content area.
 */
async function renderSchema(root, { api, session }) {
  root.innerHTML = `
    <div class="panel wide">
      <h1>Schema</h1>
      <p class="muted">Loading schema...</p>
    </div>
  `;

  try {
    const response = await api.getSchema(session.session_id);
    const tables = response.tables || [];

    root.innerHTML = `
      <div class="page">
        <div class="page-header">
          <div>
            <h2>Schema</h2>
            <p class="muted">${tables.length} tables mapped.</p>
          </div>
        </div>
        <div class="schema-layout">
          <div class="card table-card">
            <h3>Relationships</h3>
            ${buildRelationsList(tables)}
          </div>
          ${buildSchemaMap(tables)}
        </div>
      </div>
    `;
  } catch (err) {
    showToast(err instanceof Error ? err.message : 'Failed to load schema.', 'error');
    root.innerHTML = `
      <div class="panel wide">
        <h1>Schema</h1>
        <p class="error">${err instanceof Error ? err.message : 'Failed to load schema.'}</p>
      </div>
    `;
  }
}

export { renderSchema };
