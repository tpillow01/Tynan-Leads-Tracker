// Re-enables drag & drop for the Pipeline (Kanban) view.
// Requirements in HTML:
//  - Column bodies:  <div class="kanban-col-body droptarget" data-stage="new|contacted|lost|...">
//  - Cards:          <div class="kanban-card" draggable="true" data-lead-id="123">

(function () {
  let draggingCard = null;

  // Helper: find the currently dragging card
  function currentDragging() {
    return document.querySelector('.kanban-card.dragging') || draggingCard;
  }

  // ----- Column handlers -----
  document.querySelectorAll('.droptarget').forEach(col => {
    col.addEventListener('dragover', (e) => {
      // REQUIRED so drop event will fire
      e.preventDefault();
      col.classList.add('dropover');
    });

    col.addEventListener('dragleave', () => {
      col.classList.remove('dropover');
    });

    col.addEventListener('drop', async (e) => {
      e.preventDefault();
      col.classList.remove('dropover');

      const card = currentDragging();
      if (!card) return;

      // Move in DOM immediately for snappy UX
      col.appendChild(card);

      const leadId = card.dataset.leadId;
      const stage  = col.dataset.stage;

      try {
        const res = await fetch('/api/kanban/update', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lead_id: leadId, stage })
        });
        const json = await res.json().catch(() => ({}));
        if (!res.ok || !json.ok) throw new Error(json.error || 'Update failed');
      } catch (err) {
        alert('Could not update lead stage: ' + err.message);
        // Fallback: refresh to ensure UI matches DB
        location.reload();
      }
    });
  });

  // ----- Card handlers -----
  document.addEventListener('dragstart', (e) => {
    const card = e.target.closest('.kanban-card');
    if (!card) return;

    draggingCard = card;
    card.classList.add('dragging');

    // Some browsers require data to begin a valid drag
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', card.dataset.leadId || '');
  });

  document.addEventListener('dragend', (e) => {
    const card = e.target.closest('.kanban-card');
    if (card) card.classList.remove('dragging');
    draggingCard = null;
  });

  // ----- Optional: re-order within a column -----
  function handleCardReorder(e) {
    e.preventDefault();
    const targetCard = e.currentTarget;
    const dragging = currentDragging();
    if (!dragging || dragging === targetCard) return;

    const rect = targetCard.getBoundingClientRect();
    const after = (e.clientY - rect.top) > rect.height / 2;
    const parent = targetCard.parentElement;
    parent.insertBefore(dragging, after ? targetCard.nextSibling : targetCard);
  }

  function attachReorderHandlers() {
    document.querySelectorAll('.kanban-card').forEach(card => {
      card.addEventListener('dragover', handleCardReorder);
    });
  }

  attachReorderHandlers();

  // If new cards are dynamically added later, you can re-run attachReorderHandlers()
  // e.g., in a MutationObserver or after AJAX snippets are inserted.
})();
