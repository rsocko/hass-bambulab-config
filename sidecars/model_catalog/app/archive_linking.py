"""
Archive-to-model linking engine for Phase 3.3.

Implements multiple linking strategies:
1. Exact filename match
2. Fuzzy filename matching
3. Content hash matching
4. Temporal proximity matching
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import re


@dataclass
class ArchiveMetadata:
    """Archive metadata for linking."""
    archive_id: int
    name: str
    filename: str | None = None
    source_hash: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None
    source_data: dict[str, Any] | None = None


@dataclass
class LinkCandidate:
    """Candidate model for archive linking."""
    model_url: str
    model_id: str
    model_name: str
    match_method: str
    match_confidence: str
    score: float
    reasons: list[str]
    deterministic: bool = False


class ArchiveLinkingEngine:
    """Engine for linking archives to source models."""
    
    # Matching thresholds
    MIN_FILENAME_MATCH_SCORE = 0.5
    MIN_OVERALL_SCORE = 0.3
    
    # Weights for scoring
    EXACT_HASH_SCORE = 10.0
    NAME_MATCH_WEIGHT = 2.0
    FILENAME_MATCH_WEIGHT = 1.5
    TIME_PROXIMITY_WEIGHT = 0.15
    
    def __init__(self, manyfold_client: Any, db_client: Any | None = None):
        """Initialize linking engine.
        
        Args:
            manyfold_client: ManyfoldClient for fetching models
            db_client: Database client for caching (optional)
        """
        self.manyfold_client = manyfold_client
        self.db_client = db_client
        self._cache: dict[int, list[LinkCandidate]] = {}
    
    def find_candidates(
        self,
        archive: ArchiveMetadata,
        max_candidates: int = 10,
        allow_fuzzy: bool = True,
        allow_time_proximity: bool = True,
    ) -> list[LinkCandidate]:
        """Find candidate models for archive linking.
        
        Args:
            archive: Archive metadata to link
            max_candidates: Maximum candidates to return
            allow_fuzzy: Enable fuzzy matching fallback
            allow_time_proximity: Enable time-based proximity matching
            
        Returns:
            List of LinkCandidate objects sorted by score
        """
        candidates: dict[str, LinkCandidate] = {}
        
        try:
            models = self.manyfold_client.list_model_payloads()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch models: {str(e)}")
        
        # Try exact hash match first (deterministic)
        if archive.source_hash:
            hash_candidates = self._match_by_hash(archive, models)
            for candidate in hash_candidates:
                candidates[candidate.model_url] = candidate
        
        # Try exact filename match
        if archive.filename:
            filename_candidates = self._match_by_exact_filename(archive, models)
            for candidate in filename_candidates:
                if candidate.model_url not in candidates:
                    candidates[candidate.model_url] = candidate
        
        # Try fuzzy matching if enabled and no exact match found
        if allow_fuzzy and not candidates:
            fuzzy_candidates = self._match_by_fuzzy_name(archive, models)
            for candidate in fuzzy_candidates:
                if candidate.model_url not in candidates:
                    candidates[candidate.model_url] = candidate
        
        # Try time proximity if enabled
        if allow_time_proximity and archive.completed_at:
            time_candidates = self._match_by_time_proximity(archive, models)
            for candidate in time_candidates:
                if candidate.model_url in candidates:
                    # Boost existing candidate
                    existing = candidates[candidate.model_url]
                    existing.score += candidate.score * 0.3
                    existing.reasons.append(f"time proximity boost")
        
        # Sort by score and confidence
        sorted_candidates = sorted(
            candidates.values(),
            key=lambda c: (c.deterministic, c.score, self._confidence_value(c.match_confidence)),
            reverse=True
        )
        
        # Filter by minimum score
        filtered_candidates = [c for c in sorted_candidates if c.score >= self.MIN_OVERALL_SCORE]
        
        # Return top N
        return filtered_candidates[:max_candidates]
    
    def get_best_match(self, archive: ArchiveMetadata) -> LinkCandidate | None:
        """Get single best match for archive.
        
        Args:
            archive: Archive metadata to link
            
        Returns:
            Best LinkCandidate or None if no match found
        """
        candidates = self.find_candidates(archive, max_candidates=1)
        return candidates[0] if candidates else None
    
    def _match_by_hash(self, archive: ArchiveMetadata, models: list[dict]) -> list[LinkCandidate]:
        """Match archive to models by content hash.
        
        Args:
            archive: Archive with source_hash
            models: Model payloads to search
            
        Returns:
            List of matching LinkCandidate objects
        """
        if not archive.source_hash:
            return []
        
        candidates = []
        normalized_hash = archive.source_hash.lower().strip()
        
        for model in models:
            # Check various hash fields in model payload
            model_hashes = self._extract_hash_values(model)
            
            if normalized_hash in model_hashes:
                candidate = LinkCandidate(
                    model_url=str(model.get("@id") or model.get("url") or ""),
                    model_id=str(model.get("id", "")),
                    model_name=str(model.get("name", "Unknown")),
                    match_method="source_hash",
                    match_confidence="high",
                    score=self.EXACT_HASH_SCORE,
                    reasons=["exact source hash match"],
                    deterministic=True,
                )
                candidates.append(candidate)
        
        return candidates
    
    def _match_by_exact_filename(self, archive: ArchiveMetadata, models: list[dict]) -> list[LinkCandidate]:
        """Match archive to models by exact filename match.
        
        Args:
            archive: Archive with filename
            models: Model payloads to search
            
        Returns:
            List of matching LinkCandidate objects
        """
        if not archive.filename:
            return []
        
        candidates = []
        archive_stem = self._extract_filename_stem(archive.filename)
        
        for model in models:
            model_files = model.get("files", [])
            for file_obj in model_files:
                file_name = str(file_obj.get("filename", "")).strip()
                file_stem = self._extract_filename_stem(file_name)
                
                if archive_stem and archive_stem == file_stem:
                    candidate = LinkCandidate(
                        model_url=str(model.get("@id") or model.get("url") or ""),
                        model_id=str(model.get("id", "")),
                        model_name=str(model.get("name", "Unknown")),
                        match_method="exact_filename",
                        match_confidence="high",
                        score=2.0,
                        reasons=[f"exact filename match: {archive.filename}"],
                    )
                    candidates.append(candidate)
                    break
        
        return candidates
    
    def _match_by_fuzzy_name(self, archive: ArchiveMetadata, models: list[dict]) -> list[LinkCandidate]:
        """Match archive to models by fuzzy name matching.
        
        Args:
            archive: Archive with name/filename
            models: Model payloads to search
            
        Returns:
            List of matching LinkCandidate objects
        """
        candidates = []
        archive_tokens = self._tokenize_name(archive.name)
        
        if not archive_tokens:
            return candidates
        
        for model in models:
            model_name = str(model.get("name", "")).strip()
            model_tokens = self._tokenize_name(model_name)
            
            if not model_tokens:
                continue
            
            # Calculate token overlap
            overlap = archive_tokens.intersection(model_tokens)
            if not overlap:
                continue
            
            overlap_score = len(overlap) / max(len(archive_tokens), len(model_tokens))
            if overlap_score < self.MIN_FILENAME_MATCH_SCORE:
                continue
            
            score = overlap_score * self.NAME_MATCH_WEIGHT
            confidence = self._score_to_confidence(overlap_score)
            
            candidate = LinkCandidate(
                model_url=str(model.get("@id") or model.get("url") or ""),
                model_id=str(model.get("id", "")),
                model_name=model_name,
                match_method="fuzzy_name_match",
                match_confidence=confidence,
                score=score,
                reasons=[f"name overlap {overlap_score:.1%}: {', '.join(overlap)}"],
            )
            candidates.append(candidate)
        
        # Sort by score
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates
    
    def _match_by_time_proximity(self, archive: ArchiveMetadata, models: list[dict]) -> list[LinkCandidate]:
        """Match archives to models by temporal proximity.
        
        Args:
            archive: Archive with creation/completion timestamps
            models: Model payloads to search
            
        Returns:
            List of matching LinkCandidate objects
        """
        candidates = []
        
        if not archive.completed_at:
            return candidates
        
        for model in models:
            created_at_str = model.get("created_at")
            updated_at_str = model.get("updated_at")
            
            model_times = []
            for time_str in [created_at_str, updated_at_str]:
                if time_str:
                    try:
                        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                        model_times.append(dt)
                    except:
                        pass
            
            if not model_times:
                continue
            
            # Find closest timestamp
            closest_delta = None
            for model_time in model_times:
                delta = abs((archive.completed_at - model_time).total_seconds())
                if closest_delta is None or delta < closest_delta:
                    closest_delta = delta
            
            # Within 14 days?
            if closest_delta and closest_delta < (14 * 86400):  # 14 days in seconds
                days_diff = closest_delta / 86400
                score = (1.0 - (days_diff / 14.0)) * self.TIME_PROXIMITY_WEIGHT
                
                candidate = LinkCandidate(
                    model_url=str(model.get("@id") or model.get("url") or ""),
                    model_id=str(model.get("id", "")),
                    model_name=str(model.get("name", "Unknown")),
                    match_method="time_proximity",
                    match_confidence="low",
                    score=score,
                    reasons=[f"uploaded {days_diff:.0f} days from archive completion"],
                )
                candidates.append(candidate)
        
        return candidates
    
    @staticmethod
    def _extract_hash_values(model_payload: dict[str, Any]) -> set[str]:
        """Extract all hash values from model payload.
        
        Args:
            model_payload: Model dictionary to scan
            
        Returns:
            Set of normalized hash strings
        """
        hashes = set()
        hash_keys = {
            "source_hash", "source_sha256", "sha256",
            "content_hash", "file_hash", "md5"
        }
        
        def scan_value(value: Any):
            if isinstance(value, str) and value.strip():
                # Check if value looks like a hash
                if len(value) >= 32 and all(c in "0123456789abcdefABCDEF" for c in value):
                    hashes.add(value.lower())
            elif isinstance(value, dict):
                for v in value.values():
                    scan_value(v)
            elif isinstance(value, list):
                for v in value:
                    scan_value(v)
        
        for key, value in model_payload.items():
            if key.lower() in hash_keys:
                scan_value(value)
            else:
                scan_value(value)
        
        return hashes
    
    @staticmethod
    def _extract_filename_stem(filename: str) -> str:
        """Extract filename stem (without extension).
        
        Args:
            filename: Filename to process
            
        Returns:
            Normalized filename stem
        """
        # Remove extension
        stem = re.sub(r"\.[a-z0-9]{1,8}$", "", filename.lower())
        # Normalize special chars to spaces
        stem = re.sub(r"[^a-z0-9]+", " ", stem)
        # Remove extra spaces
        return re.sub(r"\s+", " ", stem).strip()
    
    @staticmethod
    def _tokenize_name(name: str) -> set[str]:
        """Tokenize name into searchable tokens.
        
        Args:
            name: Name to tokenize
            
        Returns:
            Set of tokens (min length 2)
        """
        # Extract alphanumeric words
        tokens = re.findall(r"[a-z0-9]{2,}", name.lower())
        return set(tokens)
    
    @staticmethod
    def _score_to_confidence(score: float) -> str:
        """Convert score to confidence level.
        
        Args:
            score: Score between 0 and 1
            
        Returns:
            Confidence level: "high", "medium", or "low"
        """
        if score >= 0.8:
            return "high"
        elif score >= 0.5:
            return "medium"
        else:
            return "low"
    
    @staticmethod
    def _confidence_value(confidence: str) -> float:
        """Convert confidence string to numeric value.
        
        Args:
            confidence: Confidence level
            
        Returns:
            Numeric value for sorting
        """
        values = {"high": 3.0, "medium": 2.0, "low": 1.0}
        return values.get(confidence, 0.0)
