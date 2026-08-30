/**
 * Tactical Toast Notification System
 * Zero-dependency, non-blocking alert stream replacing window.alert().
 */

let toastContainer = null;

function ensureToastContainer() {
  if (!toastContainer) {
    toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
      toastContainer = document.createElement('div');
      toastContainer.id = 'toast-container';
      toastContainer.className = 'toast-container';
      document.body.appendChild(toastContainer);
    }
  }
  return toastContainer;
}

/**
 * Show a tactical toast notification.
 * @param {string} title - Heading of the alert
 * @param {string} message - Detail message
 * @param {'info'|'success'|'warning'|'danger'} type - Visual priority
 * @param {number} duration - Milliseconds before auto-dismiss (default 4500)
 */
export function showToast(title, message, type = 'info', duration = 4500) {
  const container = ensureToastContainer();

  const toast = document.createElement('div');
  toast.className = `toast-card toast-${type}`;

  const iconMap = {
    info: 'info',
    success: 'check-circle-2',
    warning: 'alert-triangle',
    danger: 'alert-octagon',
  };
  const icon = iconMap[type] || 'bell';

  toast.innerHTML = `
    <div class="toast-icon">
      <i data-lucide="${icon}"></i>
    </div>
    <div class="toast-content">
      <div class="toast-title">${title}</div>
      <div class="toast-msg">${message}</div>
    </div>
    <button class="toast-close" title="Dismiss">&times;</button>
  `;

  const btnClose = toast.querySelector('.toast-close');
  btnClose.addEventListener('click', () => {
    dismissToast(toast);
  });

  container.appendChild(toast);
  if (window.lucide) window.lucide.createIcons();

  // Animate in
  requestAnimationFrame(() => {
    toast.classList.add('visible');
  });

  // Auto dismiss
  if (duration > 0) {
    setTimeout(() => {
      dismissToast(toast);
    }, duration);
  }
}

function dismissToast(toast) {
  if (!toast || toast.classList.contains('dismissing')) return;
  toast.classList.add('dismissing');
  toast.classList.remove('visible');
  setTimeout(() => {
    if (toast.parentElement) toast.parentElement.removeChild(toast);
  }, 300);
}
