/**
 * Similarity Scorer for Related Models
 * 
 * Calculates similarity scores between models based on:
 * - Same collection (+30 points)
 * - Same creator (+25 points)  
 * - Matching tags (+5 per tag)
 * - Matching keywords (+3 per keyword)
 * 
 * Part of Phase 3.3 implementation (Cross-System Integration)
 */

class SimilarityScorer {
  /**
   * Score similarity between two models
   * @param {Object} model1 - Base model
   * @param {Object} model2 - Compare to model
   * @returns {Object} Score and reason details
   */
  static scoreModels(model1, model2) {
    if (!model1 || !model2 || model1.model_id === model2.model_id) {
      return { score: 0, reasons: [] };
    }

    let score = 0;
    const reasons = [];

    // Collection match (+30)
    if (model1.collection_id && model1.collection_id === model2.collection_id) {
      score += 30;
      reasons.push('Same collection');
    }

    // Creator match (+25)
    if (model1.creator_id && model1.creator_id === model2.creator_id) {
      score += 25;
      reasons.push('Same creator');
    }

    // Tag matches (+5 each)
    const tags1 = this._getTags(model1);
    const tags2 = this._getTags(model2);
    const tagMatches = tags1.filter(tag => tags2.includes(tag));
    if (tagMatches.length > 0) {
      score += tagMatches.length * 5;
      reasons.push(`${tagMatches.length} matching tags`);
    }

    // Keyword matches (+3 each)
    const keywords1 = this._getKeywords(model1);
    const keywords2 = this._getKeywords(model2);
    const keywordMatches = keywords1.filter(kw => keywords2.includes(kw));
    if (keywordMatches.length > 0) {
      score += keywordMatches.length * 3;
      reasons.push(`${keywordMatches.length} matching keywords`);
    }

    // Cap score at 100%
    const normalizedScore = Math.min(100, score);

    return {
      score: normalizedScore,
      reasons,
      rawScore: score,
    };
  }

  /**
   * Find related models for a given model
   * @param {Object} model - Base model
   * @param {Array} allModels - All models to search
   * @param {Object} options - Options
   * @returns {Array} Related models sorted by score
   */
  static findRelated(model, allModels, options = {}) {
    const { limit = 5, minScore = 10 } = options;

    const related = allModels
      .filter(other => other.model_id !== model.model_id)
      .map(other => ({
        model: other,
        ...this.scoreModels(model, other),
      }))
      .filter(item => item.score >= minScore)
      .sort((a, b) => b.score - a.score)
      .slice(0, limit);

    return related;
  }

  /**
   * Get normalized tags from model
   * @private
   */
  static _getTags(model) {
    if (!model) return [];
    
    if (Array.isArray(model.tags)) {
      return model.tags.map(t => String(t).toLowerCase().trim());
    }
    if (typeof model.tags === 'string') {
      return model.tags.split(',').map(t => t.toLowerCase().trim()).filter(t => t);
    }
    return [];
  }

  /**
   * Get normalized keywords from model
   * @private
   */
  static _getKeywords(model) {
    if (!model) return [];
    
    if (Array.isArray(model.keywords)) {
      return model.keywords.map(k => String(k).toLowerCase().trim());
    }
    if (typeof model.keywords === 'string') {
      return model.keywords.split(',').map(k => k.toLowerCase().trim()).filter(k => k);
    }

    // Also extract keywords from description
    if (typeof model.description === 'string') {
      return model.description
        .toLowerCase()
        .split(/\s+/)
        .filter(w => w.length > 4 && !['this', 'that', 'with', 'from', 'into'].includes(w));
    }
    return [];
  }

  /**
   * Format score as readable text (0-100%)
   * @static
   */
  static formatScore(score) {
    const percentage = Math.round(score);
    if (percentage >= 80) return `${percentage}% match ⭐`;
    if (percentage >= 60) return `${percentage}% match 👍`;
    if (percentage >= 40) return `${percentage}% match`;
    return `${percentage}% match 📍`;
  }
}
