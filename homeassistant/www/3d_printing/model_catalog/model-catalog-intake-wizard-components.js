/**
 * Intake Wizard Components Entry Point
 * 
 * Loads all intake wizard components for model catalog intake workflow
 * Phases D-I: Source → Organize → Validate → Upload
 * 
 * Flattened structure: all components at model_catalog/ root level
 * Cache-bust versioning: increment this file's version in _resources.yaml
 */

// Phase F: State Management
import './intake-wizard-store.js?v=4';

// Phase D-E: Source Step Components
import './intake-wizard-source-summary.js?v=4';
import './intake-wizard-source-browser.js?v=4';
import './intake-wizard-source-server.js?v=4';
import './intake-wizard-source-server-summary.js?v=4';

// Phase E: Shared Components
import './intake-wizard-partial-folder-badge.js?v=4';
import './intake-wizard-return-to-source-banner.js?v=4';
import './intake-wizard-recursive-toggle.js?v=4';
import './intake-wizard-recursive-override-warning.js?v=4';
import './intake-wizard-pane-sync.js?v=4';

// Phase G: Organize Step
import './intake-wizard-organize-step.js?v=4';

// Phase H: Validate Step
import './intake-wizard-validate-step.js?v=4';

// Phase I: Upload Handler
import './intake-wizard-upload-handler.js?v=4';

console.log('✓ Intake Wizard components loaded');
