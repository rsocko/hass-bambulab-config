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
import './intake-wizard-store.js';

// Phase D-E: Source Step Components
import './intake-wizard-source-summary.js';
import './intake-wizard-source-browser.js';
import './intake-wizard-source-server.js';
import './intake-wizard-source-server-summary.js';

// Phase E: Shared Components
import './intake-wizard-partial-folder-badge.js';
import './intake-wizard-return-to-source-banner.js';
import './intake-wizard-recursive-toggle.js';
import './intake-wizard-recursive-override-warning.js';
import './intake-wizard-pane-sync.js';

// Phase G: Organize Step
import './intake-wizard-organize-step.js';

// Phase H: Validate Step
import './intake-wizard-validate-step.js';

// Phase I: Upload Handler
import './intake-wizard-upload-handler.js';

console.log('✓ Intake Wizard components loaded');
