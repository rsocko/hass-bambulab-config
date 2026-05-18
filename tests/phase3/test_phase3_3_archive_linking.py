"""
Unit tests for Phase 3.3: Archive-to-model linking.
"""

import pytest
from datetime import datetime, timezone, timedelta

from sidecars.model_catalog.app.archive_linking import (
    ArchiveMetadata, LinkCandidate, ArchiveLinkingEngine
)


class TestArchiveMetadata:
    """Test ArchiveMetadata class."""
    
    def test_archive_metadata_creation(self):
        """Test creating archive metadata."""
        archive = ArchiveMetadata(
            archive_id=123,
            name="My Print",
            filename="my_print.gcode",
            source_hash="abc123",
        )
        
        assert archive.archive_id == 123
        assert archive.name == "My Print"
        assert archive.filename == "my_print.gcode"
        assert archive.source_hash == "abc123"


class TestLinkCandidate:
    """Test LinkCandidate class."""
    
    def test_link_candidate_creation(self):
        """Test creating link candidate."""
        candidate = LinkCandidate(
            model_url="https://catalog.example.com/models/123",
            model_id="123",
            model_name="Test Model",
            match_method="fuzzy_name",
            match_confidence="high",
            score=0.85,
            reasons=["name match", "creator match"],
        )
        
        assert candidate.model_id == "123"
        assert candidate.score == 0.85
        assert len(candidate.reasons) == 2


class TestArchiveLinkingEngine:
    """Test archive linking engine."""
    
    def test_hash_extraction(self):
        """Test extracting hash values from model payload."""
        payload = {
            "id": 123,
            "name": "Model",
            "source_hash": "abc123def456",
            "details": {"sha256": "123456abcdef"},
        }
        
        hashes = ArchiveLinkingEngine._extract_hash_values(payload)
        
        assert "abc123def456" in hashes
        assert "123456abcdef" in hashes
    
    def test_filename_stem_extraction(self):
        """Test extracting filename stem."""
        assert ArchiveLinkingEngine._extract_filename_stem("model.stl") == "model"
        assert ArchiveLinkingEngine._extract_filename_stem("my-model-v2.stl") == "my model v2"
        assert ArchiveLinkingEngine._extract_filename_stem("model_part_001.STL") == "model part 001"
    
    def test_tokenization(self):
        """Test tokenizing names for matching."""
        tokens = ArchiveLinkingEngine._tokenize_name("My Awesome Model")
        
        assert "my" in tokens
        assert "awesome" in tokens
        assert "model" in tokens
        assert len(tokens) == 3
    
    def test_score_to_confidence_conversion(self):
        """Test converting scores to confidence levels."""
        assert ArchiveLinkingEngine._score_to_confidence(0.9) == "high"
        assert ArchiveLinkingEngine._score_to_confidence(0.65) == "medium"
        assert ArchiveLinkingEngine._score_to_confidence(0.3) == "low"
    
    def test_confidence_value_conversion(self):
        """Test converting confidence to numeric values."""
        assert ArchiveLinkingEngine._confidence_value("high") == 3.0
        assert ArchiveLinkingEngine._confidence_value("medium") == 2.0
        assert ArchiveLinkingEngine._confidence_value("low") == 1.0
    
    def test_mock_find_candidates_by_hash(self):
        """Test finding candidates by hash match (deterministic)."""
        mock_client = MockManyfoldClient()
        engine = ArchiveLinkingEngine(mock_client)
        
        archive = ArchiveMetadata(
            archive_id=1,
            name="Test Print",
            source_hash="abc123",  # Matches mock model 1
        )
        
        candidates = engine.find_candidates(archive)
        
        assert len(candidates) > 0
        # Best match should be deterministic hash match
        assert candidates[0].deterministic
        assert candidates[0].match_method == "source_hash"
    
    def test_mock_find_candidates_by_fuzzy_name(self):
        """Test finding candidates by fuzzy name match."""
        mock_client = MockManyfoldClient()
        engine = ArchiveLinkingEngine(mock_client)
        
        archive = ArchiveMetadata(
            archive_id=2,
            name="Awesome Test Model",  # Should match "awesome model"
        )
        
        candidates = engine.find_candidates(archive, allow_fuzzy=True)
        
        assert len(candidates) > 0
        assert not candidates[0].deterministic
        assert candidates[0].match_method == "fuzzy_name_match"
    
    def test_mock_find_candidates_by_time_proximity(self):
        """Test finding candidates by time proximity."""
        mock_client = MockCatalogClient()
        engine = ArchiveLinkingEngine(mock_client)
        
        now = datetime.now(timezone.utc)
        archive = ArchiveMetadata(
            archive_id=3,
            name="Recent Model",
            completed_at=now,
        )
        
        candidates = engine.find_candidates(archive, allow_time_proximity=True)
        
        # Should find at least one time-based candidate
        assert len(candidates) > 0
    
    def test_no_candidates_below_min_score(self):
        """Test that candidates below minimum score are filtered."""
        mock_client = MockCatalogClient()
        engine = ArchiveLinkingEngine(mock_client)
        
        archive = ArchiveMetadata(
            archive_id=4,
            name="xyz",  # Unlikely to match
        )
        
        candidates = engine.find_candidates(archive)
        
        # All candidates should have score above minimum
        for candidate in candidates:
            assert candidate.score >= engine.MIN_OVERALL_SCORE
    
    def test_get_best_match(self):
        """Test getting single best match."""
        mock_client = MockCatalogClient()
        engine = ArchiveLinkingEngine(mock_client)
        
        archive = ArchiveMetadata(
            archive_id=5,
            name="Test Model",
            source_hash="abc123",
        )
        
        best = engine.get_best_match(archive)
        
        # With hash match, should return the deterministic match
        assert best is not None
        assert best.deterministic


class MockCatalogClient:
    """Mock catalog client for testing."""
    
    def list_model_payloads(self) -> list[dict]:
        """Return mock model payloads."""
        now = datetime.now(timezone.utc).isoformat()
        
        return [
            {
                "id": "1",
                "@id": "https://catalog.example.com/models/1",
                "name": "Test Model",
                "source_hash": "abc123",  # Hash match
                "created_at": now,
                "files": [
                    {"id": 1, "filename": "model.stl", "file_type": "stl", "size": 1000},
                ],
            },
            {
                "id": "2",
                "@id": "https://catalog.example.com/models/2",
                "name": "Awesome Model",  # Fuzzy name match
                "created_at": now,
                "files": [
                    {"id": 2, "filename": "awesome.stl", "file_type": "stl", "size": 2000},
                ],
            },
            {
                "id": "3",
                "@id": "https://catalog.example.com/models/3",
                "name": "Recent Model",
                "created_at": now,  # Time proximity match
                "files": [
                    {"id": 3, "filename": "recent.stl", "file_type": "stl", "size": 3000},
                ],
            },
        ]


class TestArchiveLinkingIntegration:
    """Integration tests for archive linking."""
    
    def test_full_linking_workflow(self):
        """Test complete linking workflow from archive to model."""
        mock_client = MockCatalogClient()
        engine = ArchiveLinkingEngine(mock_client)
        
        # Create an archive that should match "Test Model"
        archive = ArchiveMetadata(
            archive_id=100,
            name="Test Model Print",
            filename="test_model.gcode",
            source_hash="abc123",
            completed_at=datetime.now(timezone.utc),
        )
        
        # Get all candidates
        candidates = engine.find_candidates(archive, max_candidates=5)
        
        assert len(candidates) > 0
        
        # Best match should be the hash match
        best_match = candidates[0]
        assert best_match.deterministic
        assert best_match.score > 0
        assert "hash" in best_match.match_method.lower()
    
    def test_multiple_fuzzy_matches(self):
        """Test ranking multiple fuzzy matches."""
        mock_client = MockCatalogClient()
        engine = ArchiveLinkingEngine(mock_client)
        
        # Archive with name that could match multiple models
        archive = ArchiveMetadata(
            archive_id=101,
            name="Model Print",
        )
        
        candidates = engine.find_candidates(archive, max_candidates=10)
        
        # Should get multiple candidates
        assert len(candidates) > 0
        
        # Higher scoring candidates should come first
        scores = [c.score for c in candidates]
        assert scores == sorted(scores, reverse=True)
