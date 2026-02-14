/*
 * table.js
 *
 * Simple HTML table renderer for admin lists.
 */

/**
 * Render a table from headers and rows.
 *
 * @param {string[]} headers
 * @param {string[][]} rows
 * @returns {string}
 */
function renderTable(headers, rows) {
  const headerHtml = headers.map((h) => `<th>${h}</th>`).join('');
  const rowHtml = rows
    .map((row) => {
      const cells = row.map((cell) => `<td>${cell}</td>`).join('');
      return `<tr>${cells}</tr>`;
    })
    .join('');

  return `
    <table class="table">
      <thead><tr>${headerHtml}</tr></thead>
      <tbody>${rowHtml}</tbody>
    </table>
  `;
}

export { renderTable };
