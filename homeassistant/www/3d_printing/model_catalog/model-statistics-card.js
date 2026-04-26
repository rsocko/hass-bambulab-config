/**
 * Model Statistics Card
 * 
 * Custom Lovelace card for displaying model print statistics and recommendations.
 * Shows success rates, print history, filament usage, and difficulty level.
 * 
 * Version: 1.0.0
 */

class ModelStatisticsCard extends HTMLElement {
  setConfig(config) {
    if (!config.model_ref) {
      throw new Error('model_ref is required');
    }
    this.config = {
      title: 'Model Statistics',
      theme: 'default',
      ...config,
    };
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 4;
  }

  _render() {
    if (!this._hass) return;

    const container = document.createElement('div');
    container.className = 'model-stats-container';

    // Build HTML
    const html = `
      <ha-card>
        <div class="card-header">
          <div class="card-title">${this.config.title || 'Model Statistics'}</div>
          <div class="card-subtitle">${this.config.model_ref}</div>
        </div>
        
        <div class="card-content">
          <div class="stats-grid">
            ${this._renderStatItem('Total Prints', this._getStatValue('total_prints', '–'))}
            ${this._renderStatItem('Success Rate', this._formatPercentage(this._getStatValue('success_rate', 0)))}
            ${this._renderStatItem('Avg Print Time', this._formatDuration(this._getStatValue('avg_print_time', 0)))}
            ${this._renderStatItem('Difficulty', this._getStatValue('difficulty_level', 'Unknown'))}
            ${this._renderStatItem('Filament Used', this._formatGrams(this._getStatValue('total_filament_used', 0)))}
            ${this._renderStatItem('Last Print', this._formatDate(this._getStatValue('last_print_date', null)))}
          </div>

          <div class="success-rate-chart">
            ${this._renderSuccessRateChart()}
          </div>

          <div class="filament-summary">
            <h3>Filament by Color</h3>
            ${this._renderFilamentSummary()}
          </div>

          ${this._renderRecommendations()}
        </div>

        <div class="card-actions">
          <mwc-button @click="${this._openModelDetail.bind(this)}">
            View Model Details
          </mwc-button>
        </div>
      </ha-card>
    `;

    container.innerHTML = html;
    container.addEventListener('click', this._handleClick.bind(this));
    
    // Apply styles
    const style = this._getStyles();
    container.appendChild(style);

    // Replace content
    while (this.firstChild) {
      this.removeChild(this.firstChild);
    }
    this.appendChild(container);
  }

  _getStatValue(key, defaultValue) {
    // In a real implementation, this would fetch from a sensor or the API
    // For now, return placeholder or configured value
    const sensorMap = {
      'total_prints': `sensor.model_${this.config.model_ref}_total_prints`,
      'success_rate': `sensor.model_${this.config.model_ref}_success_rate`,
      'avg_print_time': `sensor.model_${this.config.model_ref}_avg_print_time`,
      'difficulty_level': `sensor.model_${this.config.model_ref}_difficulty`,
      'total_filament_used': `sensor.model_${this.config.model_ref}_total_filament`,
      'last_print_date': `sensor.model_${this.config.model_ref}_last_print_date`,
    };

    const sensorId = sensorMap[key];
    if (sensorId && this._hass.states[sensorId]) {
      return this._hass.states[sensorId].state;
    }

    return defaultValue;
  }

  _renderStatItem(label, value) {
    return `
      <div class="stat-item">
        <span class="stat-label">${label}</span>
        <strong class="stat-value">${value}</strong>
      </div>
    `;
  }

  _formatPercentage(value) {
    if (!value || isNaN(value)) return '–';
    return `${(parseFloat(value) * 100).toFixed(1)}%`;
  }

  _formatDuration(seconds) {
    if (!seconds || isNaN(seconds)) return '–';
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (hours > 0) {
      return `${hours}h ${mins}m`;
    }
    return `${mins}m`;
  }

  _formatGrams(grams) {
    if (!grams || isNaN(grams)) return '–';
    return `${parseFloat(grams).toFixed(1)}g`;
  }

  _formatDate(dateStr) {
    if (!dateStr) return '–';
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString();
    } catch {
      return dateStr;
    }
  }

  _renderSuccessRateChart() {
    const successRate = parseFloat(this._getStatValue('success_rate', 0)) || 0;
    const failRate = 1 - successRate;
    const successPct = (successRate * 100).toFixed(1);
    const failPct = (failRate * 100).toFixed(1);

    return `
      <div class="chart-container">
        <div class="chart-label">Print Outcomes</div>
        <div class="chart-bar">
          <div class="bar-segment success" style="width: ${successPct}%" title="Success: ${successPct}%"></div>
          <div class="bar-segment failed" style="width: ${failPct}%" title="Failed: ${failPct}%"></div>
        </div>
        <div class="chart-legend">
          <span><span class="legend-box success"></span>Success ${successPct}%</span>
          <span><span class="legend-box failed"></span>Failed ${failPct}%</span>
        </div>
      </div>
    `;
  }

  _renderFilamentSummary() {
    // This would be populated from filament analysis data
    return `
      <div class="filament-list">
        <div class="filament-item">
          <span class="filament-color" style="background-color: #FF6B6B;"></span>
          <span class="filament-name">Red</span>
          <span class="filament-amount">125.5g</span>
        </div>
        <div class="filament-item">
          <span class="filament-color" style="background-color: #4ECDC4;"></span>
          <span class="filament-name">Teal</span>
          <span class="filament-amount">87.3g</span>
        </div>
      </div>
    `;
  }

  _renderRecommendations() {
    // This would be populated from recommendation engine data
    return `
      <div class="recommendations-section">
        <h3>Recommended Next Models</h3>
        <div class="recommendations-list">
          <div class="recommendation-item">
            <span class="recommendation-name">Gridfinity Box Large</span>
            <span class="recommendation-score">92 percent</span>
          </div>
          <div class="recommendation-item">
            <span class="recommendation-name">Cable Holder</span>
            <span class="recommendation-score">85 percent</span>
          </div>
        </div>
      </div>
    `;
  }

  _openModelDetail() {
    // Navigate to model detail view
    this._hass.callService('browser_mod', 'navigate', {
      path: `/lovelace/3d-printing/model-${this.config.model_ref}`,
    });
  }

  _handleClick(event) {
    if (event.target.classList.contains('recommendation-item')) {
      const modelName = event.target.querySelector('.recommendation-name').textContent;
      console.log(`Selected recommendation: ${modelName}`);
    }
  }

  _getStyles() {
    const styleEl = document.createElement('style');
    styleEl.textContent = `
      .model-stats-container {
        font-family: var(--primary-font-family, Roboto);
        color: var(--primary-text-color);
      }

      ha-card {
        border-radius: 12px;
        overflow: hidden;
      }

      .card-header {
        padding: 16px 16px 12px 16px;
        border-bottom: 1px solid var(--divider-color);
      }

      .card-title {
        font-size: 20px;
        font-weight: 500;
        margin-bottom: 4px;
      }

      .card-subtitle {
        font-size: 12px;
        color: var(--secondary-text-color);
      }

      .card-content {
        padding: 16px;
      }

      .stats-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 12px;
        margin-bottom: 20px;
      }

      .stat-item {
        display: flex;
        flex-direction: column;
        padding: 12px;
        background: var(--state-unavailable-color, #f5f5f5);
        border-radius: 8px;
        opacity: 0.5;
      }

      .stat-label {
        font-size: 12px;
        color: var(--secondary-text-color);
        margin-bottom: 4px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }

      .stat-value {
        font-size: 22px;
        font-weight: 700;
        color: var(--primary-text-color);
      }

      .success-rate-chart {
        margin-bottom: 20px;
        padding: 16px;
        background: var(--state-unavailable-color, #f5f5f5);
        border-radius: 8px;
        opacity: 0.5;
      }

      .chart-container {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }

      .chart-label {
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }

      .chart-bar {
        display: flex;
        height: 12px;
        border-radius: 6px;
        overflow: hidden;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
      }

      .bar-segment {
        flex: 1;
        transition: flex 0.3s ease;
      }

      .bar-segment.success {
        background: linear-gradient(90deg, #4CAF50, #66BB6A);
      }

      .bar-segment.failed {
        background: linear-gradient(90deg, #EF5350, #E53935);
      }

      .chart-legend {
        display: flex;
        gap: 16px;
        font-size: 12px;
      }

      .legend-box {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 2px;
        margin-right: 4px;
        vertical-align: middle;
      }

      .legend-box.success {
        background: #4CAF50;
      }

      .legend-box.failed {
        background: #EF5350;
      }

      .filament-summary {
        margin-bottom: 20px;
      }

      .filament-summary h3 {
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 12px;
        margin-top: 0;
      }

      .filament-list {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }

      .filament-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 8px;
        background: var(--state-unavailable-color, #f5f5f5);
        border-radius: 6px;
        opacity: 0.5;
      }

      .filament-color {
        display: inline-block;
        width: 24px;
        height: 24px;
        border-radius: 4px;
        border: 1px solid rgba(0, 0, 0, 0.1);
      }

      .filament-name {
        flex: 1;
        font-size: 12px;
      }

      .filament-amount {
        font-size: 12px;
        font-weight: 600;
        color: var(--secondary-text-color);
      }

      .recommendations-section {
        margin-top: 20px;
        padding-top: 16px;
        border-top: 1px solid var(--divider-color);
      }

      .recommendations-section h3 {
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 12px;
        margin-top: 0;
      }

      .recommendations-list {
        display: flex;
        flex-direction: column;
        gap: 8px;
      }

      .recommendation-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 12px;
        background: var(--state-unavailable-color, #f5f5f5);
        border-radius: 6px;
        cursor: pointer;
        transition: background 0.2s ease;
        opacity: 0.5;
      }

      .recommendation-item:hover {
        background: var(--primary-color);
        opacity: 0.7;
      }

      .recommendation-name {
        font-size: 12px;
        flex: 1;
      }

      .recommendation-score {
        font-size: 12px;
        font-weight: 600;
        color: var(--primary-color);
      }

      .card-actions {
        display: flex;
        justify-content: flex-end;
        gap: 8px;
        padding: 12px 16px;
        border-top: 1px solid var(--divider-color);
        background: var(--state-unavailable-color, #fafafa);
      }

      mwc-button {
        --mdc-theme-primary: var(--primary-color);
      }
    `;
    return styleEl;
  }
}

// Register custom element
customElements.define('model-statistics-card', ModelStatisticsCard);

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ModelStatisticsCard;
}
