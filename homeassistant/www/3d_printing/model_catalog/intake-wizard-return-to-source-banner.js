/**
 * Return-to-Source Banner Component
 * 
 * Displayed when user returns to Source step with existing exclusions.
 * Reminds user of prior exclusion state and allows quick review.
 * 
 * Usage:
 * <return-to-source-banner
 *   excludedCount="5"
 *   onViewExclusions={(e) => handleViewExclusions()}
 * />
 */

class ReturnToSourceBanner extends HTMLElement {
  connectedCallback() {
    this.render();
    this.addEventListener('click', (e) => this._handleClick(e));
  }

  disconnectedCallback() {
    this.removeEventListener('click', this._handleClick);
  }

  render() {
    const excludedCount = parseInt(this.getAttribute('excluded-count') || '0', 10);
    const isFirstVisit = this.getAttribute('is-first-visit') === 'true';

    if (isFirstVisit || excludedCount === 0) {
      this.innerHTML = '';
      return;
    }

    this.innerHTML = `
      <style>
        :host {
          --banner-bg: #fff3cd;
          --banner-border: #ffc107;
          --banner-text: #856404;
          --banner-button: #ffc107;
        }

        .return-banner {
          background-color: var(--banner-bg);
          border-left: 4px solid var(--banner-border);
          border-radius: 2px;
          padding: 12px 16px;
          margin-bottom: 16px;
          display: flex;
          align-items: center;
          gap: 12px;
          font-size: 14px;
          color: var(--banner-text);
        }

        .banner-icon {
          flex-shrink: 0;
          font-size: 18px;
          line-height: 1;
        }

        .banner-content {
          flex: 1;
          line-height: 1.4;
        }

        .banner-title {
          font-weight: 600;
          margin-bottom: 4px;
        }

        .banner-description {
          font-size: 13px;
          opacity: 0.9;
        }

        .banner-actions {
          display: flex;
          gap: 8px;
          flex-shrink: 0;
        }

        .banner-button {
          padding: 6px 12px;
          border: 1px solid var(--banner-border);
          background-color: transparent;
          color: var(--banner-text);
          border-radius: 3px;
          cursor: pointer;
          font-size: 13px;
          font-weight: 500;
          transition: all 0.2s ease;
        }

        .banner-button:hover {
          background-color: rgba(255, 193, 7, 0.1);
          border-color: #ffb300;
        }

        .banner-button:active {
          background-color: rgba(255, 193, 7, 0.2);
        }

        .banner-close {
          flex-shrink: 0;
          background: none;
          border: none;
          color: var(--banner-text);
          cursor: pointer;
          font-size: 18px;
          line-height: 1;
          padding: 0;
          width: 24px;
          height: 24px;
          display: flex;
          align-items: center;
          justify-content: center;
          opacity: 0.7;
          transition: opacity 0.2s ease;
        }

        .banner-close:hover {
          opacity: 1;
        }

        @media (max-width: 600px) {
          .return-banner {
            flex-direction: column;
            align-items: flex-start;
            gap: 12px;
          }

          .banner-actions {
            width: 100%;
            flex-direction: column;
          }

          .banner-button {
            width: 100%;
          }
        }
      </style>

      <div class="return-banner">
        <div class="banner-icon">⚠️</div>
        <div class="banner-content">
          <div class="banner-title">Previous exclusions detected</div>
          <div class="banner-description">
            You previously excluded ${excludedCount} item${excludedCount !== 1 ? 's' : ''} from this selection.
            Would you like to review or clear them?
          </div>
        </div>
        <div class="banner-actions">
          <button class="banner-button" data-action="view-exclusions">
            View Exclusions
          </button>
          <button class="banner-button" data-action="clear-exclusions">
            Clear All
          </button>
        </div>
        <button class="banner-close" data-action="dismiss" aria-label="Close banner">
          ✕
        </button>
      </div>
    `;
  }

  _handleClick(e) {
    const target = e.target;
    if (target.classList.contains('banner-button') || target.classList.contains('banner-close')) {
      const action = target.getAttribute('data-action');
      this._dispatchAction(action);
    }
  }

  _dispatchAction(action) {
    const event = new CustomEvent('banner-action', {
      detail: { action },
      bubbles: true,
      cancelable: true
    });

    this.dispatchEvent(event);

    if (action === 'dismiss') {
      this.innerHTML = '';
    }
  }

  /**
   * Update excluded count and re-render
   */
  setExcludedCount(count) {
    this.setAttribute('excluded-count', count);
    this.render();
  }

  /**
   * Hide banner
   */
  hide() {
    this.innerHTML = '';
  }
}

customElements.define('return-to-source-banner', ReturnToSourceBanner);
export { ReturnToSourceBanner };
