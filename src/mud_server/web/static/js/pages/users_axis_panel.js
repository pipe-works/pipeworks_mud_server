/*
 * users_axis_panel.js
 *
 * Axis-state rendering helpers for the admin Users page.
 */

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

function formatAxisScore(score) {
  if (typeof score !== 'number') {
    return '—';
  }
  return score.toFixed(2);
}

/**
 * Convert technical event keys into a human-readable title.
 *
 * @param {string} eventType
 * @returns {string}
 */
function formatEventTypeLabel(eventType) {
  if (!eventType) {
    return 'Event';
  }
  return String(eventType)
    .replace(/[_-]+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/**
 * Derive a compact summary that explains what the axis event actually did.
 *
 * @param {object} event
 * @returns {string}
 */
function buildAxisEventSummary(event) {
  const description =
    event?.event_type_description && String(event.event_type_description).trim();
  if (description) {
    return description;
  }

  const metadata = event?.metadata || {};
  const summary = metadata.summary || metadata.reason || metadata.message || '';
  if (summary) {
    return String(summary);
  }

  const action = metadata.action ? String(metadata.action) : '';
  const source = metadata.source ? String(metadata.source) : '';
  if (action && source) {
    return `${action} (${source})`;
  }
  if (action) {
    return action;
  }
  if (source) {
    return source;
  }

  const deltas = Array.isArray(event?.deltas) ? event.deltas : [];
  if (deltas.length === 1) {
    const [delta] = deltas;
    const axisName = delta?.axis_name ? String(delta.axis_name) : 'Axis';
    const change = Number(delta?.delta);
    if (Number.isFinite(change)) {
      if (change > 0) {
        return `${axisName} increased by ${formatAxisScore(change)}`;
      }
      if (change < 0) {
        return `${axisName} decreased by ${formatAxisScore(Math.abs(change))}`;
      }
    }
    return `${axisName} was updated`;
  }

  if (deltas.length > 1) {
    return `${deltas.length} axis values updated`;
  }

  return 'No additional event details.';
}

/**
 * Build the axis-state tab body.
 *
 * @param {object} params
 * @param {Array<object>} params.characters
 * @param {number|null} params.axisCharacterId
 * @param {object|null} params.axisState
 * @param {Array<object>|null} params.axisEvents
 * @param {boolean} params.isLoading
 * @param {boolean} params.eventsLoading
 * @param {string|null} params.error
 * @param {string|null} params.eventsError
 * @returns {string}
 */
function buildAxisStatePanel({
  characters,
  axisCharacterId,
  axisState,
  axisEvents,
  isLoading,
  eventsLoading,
  error,
  eventsError,
}) {
  if (!characters.length) {
    return '<p class="u-muted">No characters available for axis state.</p>';
  }

  const optionsHtml = characters
    .map(
      (character) =>
        `<option value="${character.id}" ${
          Number(character.id) === axisCharacterId ? 'selected' : ''
        }>${escapeHtml(character.name)}</option>`
    )
    .join('');

  if (error) {
    return `
      <div class="axis-state">
        <label class="detail-form axis-state-select">
          Character
          <select class="select" data-axis-character>${optionsHtml}</select>
        </label>
        <p class="error">${escapeHtml(error)}</p>
      </div>
    `;
  }

  if (isLoading || !axisState) {
    return `
      <div class="axis-state">
        <label class="detail-form axis-state-select">
          Character
          <select class="select" data-axis-character>${optionsHtml}</select>
        </label>
        <p class="u-muted">Loading axis state...</p>
      </div>
    `;
  }

  const axisRows = axisState.axes?.length
    ? axisState.axes
        .map(
          (axis) => `
            <div>
              <dt>${escapeHtml(axis.axis_name)}</dt>
              <dd>${escapeHtml(axis.axis_label || '—')} (${formatAxisScore(
                axis.axis_score
              )})</dd>
            </div>
          `
        )
        .join('')
    : '<p class="u-muted">No axis scores recorded.</p>';

  const snapshot =
    axisState.current_state && Object.keys(axisState.current_state).length
      ? JSON.stringify(axisState.current_state, null, 2)
      : null;

  const eventsBody = () => {
    if (eventsError) {
      return `<p class="error">${escapeHtml(eventsError)}</p>`;
    }
    if (eventsLoading) {
      return '<p class="u-muted">Loading events...</p>';
    }
    if (!axisEvents || axisEvents.length === 0) {
      return '<p class="u-muted">No axis events recorded.</p>';
    }

    return axisEvents
      .map((event) => {
        const eventLabel = formatEventTypeLabel(event.event_type);
        const eventSummary = buildAxisEventSummary(event);
        const metadata = event.metadata || {};
        const metadataHtml = Object.keys(metadata).length
          ? `
            <div class="tag-list axis-event-tags">
              ${Object.entries(metadata)
                .map(
                  ([key, value]) =>
                    `<span class="tag">${escapeHtml(key)}: ${escapeHtml(value)}</span>`
                )
                .join('')}
            </div>
          `
          : '<p class="u-muted">No metadata.</p>';

        const deltaHtml = event.deltas
          .map(
            (delta) => `
              <div class="axis-event-delta">
                <span class="axis-event-axis">${escapeHtml(delta.axis_name)}</span>
                <span class="axis-event-values">
                  ${formatAxisScore(delta.old_score)} → ${formatAxisScore(delta.new_score)}
                </span>
                <span class="axis-event-change">${formatAxisScore(delta.delta)}</span>
              </div>
            `
          )
          .join('');

        return `
          <div class="axis-event">
            <div class="axis-event-header">
              <div>
                <div class="axis-event-title">${escapeHtml(eventLabel)}</div>
                <div class="axis-event-kind">${escapeHtml(event.event_type)}</div>
                <div class="axis-event-summary">${escapeHtml(eventSummary)}</div>
                <div class="axis-event-sub">${escapeHtml(event.timestamp || '—')}</div>
              </div>
              <div class="axis-event-world">${escapeHtml(event.world_id)}</div>
            </div>
            <div class="axis-event-deltas">${deltaHtml}</div>
            <div class="axis-event-meta">
              ${metadataHtml}
            </div>
          </div>
        `;
      })
      .join('');
  };

  return `
    <div class="axis-state">
      <label class="detail-form axis-state-select">
        Character
        <select class="select" data-axis-character>${optionsHtml}</select>
      </label>
      <dl class="detail-list axis-state-summary">
        <div><dt>World</dt><dd>${escapeHtml(axisState.world_id)}</dd></div>
        <div><dt>Seed</dt><dd>${axisState.state_seed ?? '—'}</dd></div>
        <div><dt>Policy</dt><dd>${escapeHtml(axisState.state_version || '—')}</dd></div>
        <div><dt>Updated</dt><dd>${escapeHtml(axisState.state_updated_at || '—')}</dd></div>
      </dl>
      <h5>Axis Scores</h5>
      <dl class="detail-list axis-score-list">${axisRows}</dl>
      <h5>Current Snapshot</h5>
      ${
        snapshot
          ? `<pre class="detail-code">${escapeHtml(snapshot)}</pre>`
          : '<p class="u-muted">No snapshot data available.</p>'
      }
      <h5>Recent Axis Events</h5>
      <div class="axis-event-list">
        ${eventsBody()}
      </div>
    </div>
  `;
}

export { buildAxisStatePanel };
