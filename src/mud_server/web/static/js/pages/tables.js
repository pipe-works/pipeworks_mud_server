/*
 * tables.js
 *
 * Admin database browser:
 * - select a table from schema metadata
 * - browse paginated row data
 */

import { showToast } from '../ui/toasts.js';

const DEFAULT_PAGE_SIZE = 100;
const PAGE_SIZE_OPTIONS = [25, 50, 100, 250, 500];

function escapeHtml(value) {
  if (value === null || value === undefined) {
    return '';
  }
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function normalizeNumber(value, fallback = 0) {
  const asNumber = Number(value);
  return Number.isFinite(asNumber) ? asNumber : fallback;
}

function normalizeCellValue(value) {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch (_err) {
      return String(value);
    }
  }
  return String(value);
}

function renderCell(value) {
  const normalized = normalizeCellValue(value);
  if (normalized === null) {
    return '<span class="table-cell-null">NULL</span>';
  }
  if (normalized.length === 0) {
    return '<span class="u-muted">(empty)</span>';
  }
  return escapeHtml(normalized);
}

function getSelectedTable(tables, selectedTableName) {
  if (!selectedTableName) {
    return null;
  }
  return tables.find((table) => table.name === selectedTableName) || null;
}

function parseTableToken(value) {
  if (!value) {
    return '';
  }
  try {
    return decodeURIComponent(value);
  } catch (_err) {
    return '';
  }
}

function buildTablesListRows(tables, selectedTableName) {
  if (!tables.length) {
    return `
      <tr>
        <td class="table-empty" colspan="3">No database tables found.</td>
      </tr>
    `;
  }

  return tables
    .map((table) => {
      const tableName = String(table.name || '');
      const rowCount = normalizeNumber(table.row_count, 0);
      const columnCount = Array.isArray(table.columns) ? table.columns.length : 0;
      const isSelected = tableName === selectedTableName;
      const rowClass = `is-selectable ${isSelected ? 'is-selected' : ''}`.trim();
      return `
        <tr class="${rowClass}" data-select-table="${encodeURIComponent(tableName)}">
          <td><code>${escapeHtml(tableName)}</code></td>
          <td>${rowCount.toLocaleString()}</td>
          <td>${columnCount}</td>
        </tr>
      `;
    })
    .join('');
}

function buildRowsTable(columns, rows, offset) {
  if (!columns.length) {
    return '<p class="u-muted">No columns discovered for this table.</p>';
  }

  const headers = columns.map((columnName) => `<th>${escapeHtml(columnName)}</th>`).join('');
  const bodyRows = rows.length
    ? rows
        .map((row, rowIndex) => {
          const rowNumber = offset + rowIndex + 1;
          const cells = columns
            .map((_, cellIndex) => `<td class="tables-data-cell">${renderCell(row[cellIndex])}</td>`)
            .join('');
          return `
            <tr>
              <td class="tables-row-index">${rowNumber}</td>
              ${cells}
            </tr>
          `;
        })
        .join('')
    : `
      <tr>
        <td class="table-empty" colspan="${columns.length + 1}">No rows in this range.</td>
      </tr>
    `;

  return `
    <div class="table-wrap tables-data-wrap">
      <table class="table tables-data-table">
        <thead>
          <tr>
            <th class="tables-row-index">#</th>
            ${headers}
          </tr>
        </thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </div>
  `;
}

async function renderTables(root, { api, session }) {
  const sessionId = session.session_id;
  const state = {
    tables: [],
    selectedTableName: null,
    columns: [],
    rows: [],
    limit: DEFAULT_PAGE_SIZE,
    offset: 0,
    loadingRows: false,
    rowError: '',
    requestSequence: 0,
  };

  function render() {
    const selectedTable = getSelectedTable(state.tables, state.selectedTableName);
    const rowCount = normalizeNumber(selectedTable?.row_count, 0);
    const pageStart = rowCount > 0 ? state.offset + 1 : 0;
    const pageEnd = rowCount > 0 ? Math.min(state.offset + state.rows.length, rowCount) : 0;
    const canMovePrevious = state.offset > 0 && !state.loadingRows;
    const canMoveNext = !!selectedTable && !state.loadingRows && state.offset + state.rows.length < rowCount;

    const pageSizeOptions = PAGE_SIZE_OPTIONS.map((option) => {
      const selected = option === state.limit ? 'selected' : '';
      return `<option value="${option}" ${selected}>${option} rows</option>`;
    }).join('');

    let browserBody = '<p class="u-muted">Select a table to browse rows.</p>';
    if (selectedTable) {
      const browserStatus = state.loadingRows
        ? 'Loading rows...'
        : `${pageStart.toLocaleString()}-${pageEnd.toLocaleString()} of ${rowCount.toLocaleString()}`;
      const tableRowsHtml = state.rowError
        ? `<p class="error">${escapeHtml(state.rowError)}</p>`
        : buildRowsTable(state.columns, state.rows, state.offset);

      browserBody = `
        <div class="table-toolbar tables-browser-toolbar">
          <div class="tables-browser-status">
            ${browserStatus}
          </div>
          <div class="tables-browser-controls">
            <label class="table-search tables-page-size-control">
              Page size
              <select class="select tables-page-size" data-page-size>
                ${pageSizeOptions}
              </select>
            </label>
            <button class="btn btn--secondary btn--sm" type="button" data-refresh-rows ${state.loadingRows ? 'disabled' : ''}>
              Refresh
            </button>
            <button class="btn btn--secondary btn--sm" type="button" data-prev-page ${canMovePrevious ? '' : 'disabled'}>
              Previous
            </button>
            <button class="btn btn--secondary btn--sm" type="button" data-next-page ${canMoveNext ? '' : 'disabled'}>
              Next
            </button>
          </div>
        </div>
        ${tableRowsHtml}
      `;
    }

    root.innerHTML = `
      <div class="page">
        <div class="page-header">
          <div>
            <h2>Database Browser</h2>
            <p class="u-muted">${state.tables.length} tables available. Select one to inspect live rows.</p>
          </div>
        </div>
        <div class="split-layout tables-browser-layout">
          <div class="card table-card tables-list-card">
            <h3>Tables</h3>
            <div class="table-wrap">
              <table class="table tables-list-table">
                <thead>
                  <tr>
                    <th>Table</th>
                    <th>Rows</th>
                    <th>Cols</th>
                  </tr>
                </thead>
                <tbody>
                  ${buildTablesListRows(state.tables, state.selectedTableName)}
                </tbody>
              </table>
            </div>
          </div>
          <div class="card table-card tables-data-card">
            <div class="tab-header">
              <div>
                <h3>Rows</h3>
                <p class="u-muted">
                  ${selectedTable ? `<code>${escapeHtml(selectedTable.name)}</code>` : 'No table selected'}
                </p>
              </div>
            </div>
            ${browserBody}
          </div>
        </div>
      </div>
    `;
  }

  async function loadRows() {
    const selectedTable = getSelectedTable(state.tables, state.selectedTableName);
    if (!selectedTable) {
      state.columns = [];
      state.rows = [];
      state.loadingRows = false;
      state.rowError = '';
      render();
      return;
    }

    state.loadingRows = true;
    state.rowError = '';
    const requestId = state.requestSequence + 1;
    state.requestSequence = requestId;
    render();

    try {
      const response = await api.getTableRows(
        sessionId,
        selectedTable.name,
        state.limit,
        state.offset
      );
      if (requestId !== state.requestSequence) {
        return;
      }
      state.columns = Array.isArray(response.columns) ? response.columns : [];
      state.rows = Array.isArray(response.rows) ? response.rows : [];
      state.rowError = '';
    } catch (err) {
      if (requestId !== state.requestSequence) {
        return;
      }
      const message = err instanceof Error ? err.message : 'Failed to load table rows.';
      state.columns = [];
      state.rows = [];
      state.rowError = message;
      showToast(message, 'error');
    } finally {
      if (requestId === state.requestSequence) {
        state.loadingRows = false;
        render();
      }
    }
  }

  async function selectTable(tableName) {
    if (!tableName || tableName === state.selectedTableName) {
      return;
    }
    state.selectedTableName = tableName;
    state.offset = 0;
    state.columns = [];
    state.rows = [];
    state.rowError = '';
    await loadRows();
  }

  root.addEventListener('click', async (event) => {
    const target = event.target;
    if (!(target instanceof Element)) {
      return;
    }

    const tableRow = target.closest('[data-select-table]');
    if (tableRow && root.contains(tableRow)) {
      const tableName = parseTableToken(tableRow.getAttribute('data-select-table'));
      if (tableName) {
        await selectTable(tableName);
      }
      return;
    }

    const refreshButton = target.closest('[data-refresh-rows]');
    if (refreshButton && root.contains(refreshButton)) {
      await loadRows();
      return;
    }

    const previousButton = target.closest('[data-prev-page]');
    if (previousButton && root.contains(previousButton)) {
      if (state.offset === 0 || state.loadingRows) {
        return;
      }
      state.offset = Math.max(0, state.offset - state.limit);
      await loadRows();
      return;
    }

    const nextButton = target.closest('[data-next-page]');
    if (nextButton && root.contains(nextButton)) {
      const selectedTable = getSelectedTable(state.tables, state.selectedTableName);
      const rowCount = normalizeNumber(selectedTable?.row_count, 0);
      const nextOffset = state.offset + state.limit;
      if (state.loadingRows || nextOffset >= rowCount) {
        return;
      }
      state.offset = nextOffset;
      await loadRows();
    }
  });

  root.addEventListener('change', async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) {
      return;
    }
    if (!target.matches('[data-page-size]')) {
      return;
    }

    const nextSize = Number(target.value);
    if (!Number.isFinite(nextSize) || nextSize < 1 || nextSize === state.limit) {
      return;
    }

    state.limit = nextSize;
    state.offset = 0;
    await loadRows();
  });

  root.innerHTML = `
    <div class="auth-panel wide">
      <h1>Database Browser</h1>
      <p class="u-muted">Loading tables...</p>
    </div>
  `;

  try {
    const response = await api.getTables(sessionId);
    state.tables = Array.isArray(response.tables) ? response.tables : [];
    state.selectedTableName = state.tables.length ? String(state.tables[0].name || '') : null;
    render();
    if (state.selectedTableName) {
      await loadRows();
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to load tables.';
    showToast(message, 'error');
    root.innerHTML = `
      <div class="auth-panel wide">
        <h1>Database Browser</h1>
        <p class="error">${escapeHtml(message)}</p>
      </div>
    `;
  }
}

export { renderTables };
