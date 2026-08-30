/**
 * In-App Tactical Confirmation Modal
 * Replaces window.confirm() with non-blocking Promise-based dialog.
 */

export function confirmModal({
  title = 'Confirm Operator Action',
  message = 'Are you sure you want to proceed?',
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  danger = false,
}) {
  return new Promise((resolve) => {
    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop visible';

    const dialog = document.createElement('div');
    dialog.className = 'modal-dialog tactical-confirm-dialog';

    dialog.innerHTML = `
      <div class="modal-header">
        <div class="modal-title">
          <i data-lucide="${danger ? 'alert-triangle' : 'help-circle'}" style="color: ${danger ? '#ef4444' : '#38bdf8'};"></i>
          <span>${title}</span>
        </div>
        <button class="modal-close-btn">&times;</button>
      </div>
      <div class="modal-body">
        <p class="confirm-message">${message}</p>
      </div>
      <div class="modal-footer">
        <button class="btn-cancel">${cancelText}</button>
        <button class="btn-confirm ${danger ? 'btn-danger' : 'btn-primary'}">${confirmText}</button>
      </div>
    `;

    backdrop.appendChild(dialog);
    document.body.appendChild(backdrop);
    if (window.lucide) window.lucide.createIcons();

    function cleanup(result) {
      backdrop.classList.remove('visible');
      setTimeout(() => {
        if (backdrop.parentElement) backdrop.parentElement.removeChild(backdrop);
      }, 200);
      resolve(result);
    }

    dialog.querySelector('.btn-confirm').addEventListener('click', () => cleanup(true));
    dialog.querySelector('.btn-cancel').addEventListener('click', () => cleanup(false));
    dialog.querySelector('.modal-close-btn').addEventListener('click', () => cleanup(false));

    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) cleanup(false);
    });
  });
}
