import math
import unittest
from copy import deepcopy

EMPTY_UUID = "00000000000000000000000000000000"


def _norm_color(value):
    value = (value or "").strip().lower()
    if value.startswith("#"):
        value = value[1:]
    if len(value) == 8:
        value = value[:6]
    return value


def _norm_uuid(value):
    return (value or "").strip().strip('"').lower()


def _norm_multi_hexes(value):
    raw = (value or "").strip().replace('"', '').lower()
    if not raw:
        return []
    normalized = []
    for token in raw.split(','):
        color = _norm_color(token)
        if len(color) == 6:
            normalized.append(color)
    return normalized


def _is_valid_uuid(value):
    value = _norm_uuid(value)
    if not value:
        return False
    if value == EMPTY_UUID:
        return False
    if all(ch == "0" for ch in value):
        return False
    return True


def match_tray_to_spool(tray, spools):
    """
    Deterministic test implementation of Option A matching rules.

    This mirrors the intended algorithmic behavior documented in
    docs/features/spoolman_sync/spool-matching-design-analysis.md.
    """
    tray_uuid = _norm_uuid(tray.get("tray_uuid"))
    tray_color = _norm_color(tray.get("color"))
    tray_material = tray.get("type", "")
    tray_profile_name = tray.get("name", "")
    enable_multi_any_hex_fallback = True

    unsealed = [s for s in spools if not bool(s.get("extra_sealed", False))]

    match = []
    match_reason = None
    match_strategy = None
    tried_uuid = False
    is_bambu_path = False

    if _is_valid_uuid(tray_uuid):
        tried_uuid = True
        is_bambu_path = True
        match = [s for s in unsealed if _norm_uuid(s.get("extra_spool_uuid")) == tray_uuid]
        if len(match) > 1:
            return {
                "success": False,
                "spool_id": None,
                "reason": f"Multiple spools with UUID {tray_uuid} - ensure UUIDs are unique",
                "match_strategy": None,
            }
        if len(match) == 1:
            return {
                "success": True,
                "spool_id": match[0]["id"],
                "reason": None,
                "match_strategy": "uuid",
            }

    # UUID was unavailable or did not resolve a unique match.
    # Detect Bambu path from profile name when UUID is unavailable (e.g., external spool)
    if not is_bambu_path and tray_profile_name.startswith("Bambu"):
        is_bambu_path = True

    single_candidates = []
    multi_first_candidates = []
    multi_any_candidates = []
    for spool in unsealed:
        spool_color = _norm_color(spool.get("filament_color_hex"))
        spool_multi_hexes = _norm_multi_hexes(spool.get("filament_multi_color_hexes"))
        spool_multi_first = spool_multi_hexes[0] if spool_multi_hexes else ""
        spool_material = spool.get("filament_material", "")
        spool_vendor = spool.get("filament_vendor_name", "")
        spool_profile = (spool.get("filament_extra_profile_name", "") or spool.get("extra_profile_name", "")).strip('"')

        vendor_ok = (spool_vendor == "Bambu Lab") if is_bambu_path else (spool_vendor != "Bambu Lab")
        profile_ok = True
        if is_bambu_path and tray_profile_name and spool_profile:
            profile_ok = spool_profile == tray_profile_name

        if spool_material == tray_material and vendor_ok and profile_ok:
            if spool_color == tray_color:
                single_candidates.append(spool)
            if spool_multi_first == tray_color:
                multi_first_candidates.append(spool)
            if enable_multi_any_hex_fallback and tray_color in spool_multi_hexes:
                multi_any_candidates.append(spool)

    if single_candidates:
        candidates = single_candidates
        tier_strategy = "color_type"
    elif multi_first_candidates:
        candidates = multi_first_candidates
        tier_strategy = "multicolor_first_hex"
    elif multi_any_candidates:
        candidates = multi_any_candidates
        tier_strategy = "multicolor_any_hex"
    else:
        candidates = []
        tier_strategy = None

    if len(candidates) == 1:
        return {
            "success": True,
            "spool_id": candidates[0]["id"],
            "reason": None,
            "match_strategy": tier_strategy,
        }

    if len(candidates) > 1:
        ams_matches = [s for s in candidates if s.get("location") == "AMS"]
        if len(ams_matches) == 1:
            return {
                "success": True,
                "spool_id": ams_matches[0]["id"],
                "reason": None,
                "match_strategy": f"{tier_strategy}_ams_preference",
            }
        if len(ams_matches) > 1:
            return {
                "success": False,
                "spool_id": None,
                "reason": (
                    f"Multiple unsealed spools with color #{tray_color} "
                    f"and type {tray_material} found in AMS"
                ),
                "match_strategy": None,
            }
        return {
            "success": False,
            "spool_id": None,
            "reason": (
                f"Multiple unsealed spools with color #{tray_color} "
                f"and type {tray_material}, none in AMS"
            ),
            "match_strategy": None,
        }

    if tried_uuid:
        match_reason = (
            f"No unsealed Bambu spool matched UUID {tray_uuid} "
            f"or color #{tray_color} and type {tray_material}"
        )
    else:
        match_reason = f"No unsealed spool with color #{tray_color} and type {tray_material}"

    return {
        "success": False,
        "spool_id": None,
        "reason": match_reason,
        "match_strategy": None,
    }


class OptionAMatchingTests(unittest.TestCase):
    def setUp(self):
        self.base_spools = [
            {
                "id": 101,
                "extra_spool_uuid": "abc123",
                "filament_color_hex": "#FF0000",
                "filament_material": "PLA",
                "filament_vendor_name": "Bambu Lab",
                "filament_extra_profile_name": "Bambu PLA Basic",
                "location": "AMS",
                "extra_sealed": False,
            },
            {
                "id": 102,
                "extra_spool_uuid": "",
                "filament_color_hex": "#FF0000",
                "filament_material": "PLA",
                "filament_vendor_name": "Polymaker",
                "filament_extra_profile_name": "",
                "location": "Shelf",
                "extra_sealed": False,
            },
            {
                "id": 103,
                "extra_spool_uuid": "",
                "filament_color_hex": "#FF0000",
                "filament_material": "PETG",
                "filament_vendor_name": "Polymaker",
                "filament_extra_profile_name": "",
                "location": "Shelf",
                "extra_sealed": False,
            },
            {
                "id": 104,
                "extra_spool_uuid": "",
                "filament_color_hex": "#FF0000",
                "filament_material": "PLA",
                "filament_vendor_name": "eSUN",
                "filament_extra_profile_name": "",
                "location": "AMS",
                "extra_sealed": False,
            },
            {
                "id": 105,
                "extra_spool_uuid": "",
                "filament_color_hex": "#00FF00",
                "filament_material": "PLA",
                "filament_vendor_name": "Polymaker",
                "filament_extra_profile_name": "",
                "location": "Shelf",
                "extra_sealed": True,
            },
        ]

    def test_uuid_exact_match(self):
        tray = {"tray_uuid": "abc123", "color": "#ff0000", "type": "PLA", "name": "Bambu PLA Basic"}
        result = match_tray_to_spool(tray, self.base_spools)
        self.assertTrue(result["success"])
        self.assertEqual(result["spool_id"], 101)
        self.assertEqual(result["match_strategy"], "uuid")

    def test_uuid_duplicate_fails(self):
        spools = deepcopy(self.base_spools)
        dup = deepcopy(spools[0])
        dup["id"] = 999
        spools.append(dup)
        tray = {"tray_uuid": "abc123", "color": "#ff0000", "type": "PLA", "name": "Bambu PLA Basic"}
        result = match_tray_to_spool(tray, spools)
        self.assertFalse(result["success"])
        self.assertIn("Multiple spools with UUID", result["reason"])

    def test_uuid_miss_falls_back_to_bambu_color_type_profile(self):
        spools = deepcopy(self.base_spools)
        spools.append(
            {
                "id": 106,
                "extra_spool_uuid": "",
                "filament_color_hex": "#123456",
                "filament_material": "PLA",
                "filament_vendor_name": "Bambu Lab",
                "filament_extra_profile_name": "Bambu PETG Basic",
                "location": "Shelf",
                "extra_sealed": False,
            }
        )
        spools.append(
            {
                "id": 107,
                "extra_spool_uuid": "",
                "filament_color_hex": "#123456",
                "filament_material": "PLA",
                "filament_vendor_name": "Bambu Lab",
                "filament_extra_profile_name": "Bambu PLA Basic",
                "location": "AMS",
                "extra_sealed": False,
            }
        )
        tray = {
            "tray_uuid": "does-not-exist",
            "color": "#123456",
            "type": "PLA",
            "name": "Bambu PLA Basic",
        }
        result = match_tray_to_spool(tray, spools)
        self.assertTrue(result["success"])
        self.assertEqual(result["spool_id"], 107)

    def test_non_bambu_color_type_match(self):
        tray = {"tray_uuid": "", "color": "#ff0000", "type": "PETG", "name": "Any"}
        result = match_tray_to_spool(tray, self.base_spools)
        self.assertTrue(result["success"])
        self.assertEqual(result["spool_id"], 103)
        self.assertEqual(result["match_strategy"], "color_type")

    def test_same_color_different_material_prefers_type(self):
        tray = {"tray_uuid": "", "color": "#ff0000", "type": "PLA", "name": "Any"}
        result = match_tray_to_spool(tray, self.base_spools)
        # Two non-Bambu PLA candidates exist (102 shelf, 104 AMS), should AMS prefer.
        self.assertTrue(result["success"])
        self.assertEqual(result["spool_id"], 104)
        self.assertEqual(result["match_strategy"], "color_type_ams_preference")

    def test_multiple_in_ams_is_error(self):
        spools = deepcopy(self.base_spools)
        spools.append(
            {
                "id": 108,
                "extra_spool_uuid": "",
                "filament_color_hex": "#FF0000",
                "filament_material": "PLA",
                "filament_vendor_name": "Overture",
                "filament_extra_profile_name": "",
                "location": "AMS",
                "extra_sealed": False,
            }
        )
        tray = {"tray_uuid": "", "color": "#ff0000", "type": "PLA", "name": "Any"}
        result = match_tray_to_spool(tray, spools)
        self.assertFalse(result["success"])
        self.assertIn("found in AMS", result["reason"])

    def test_sealed_spools_are_excluded(self):
        tray = {"tray_uuid": "", "color": "#00ff00", "type": "PLA", "name": "Any"}
        result = match_tray_to_spool(tray, self.base_spools)
        self.assertFalse(result["success"])
        self.assertIn("No unsealed spool", result["reason"])

    def test_bambu_profile_name_can_disambiguate(self):
        spools = [
            {
                "id": 201,
                "extra_spool_uuid": "",
                "filament_color_hex": "#112233",
                "filament_material": "PLA",
                "filament_vendor_name": "Bambu Lab",
                "filament_extra_profile_name": "Bambu PLA Matte",
                "location": "AMS",
                "extra_sealed": False,
            },
            {
                "id": 202,
                "extra_spool_uuid": "",
                "filament_color_hex": "#112233",
                "filament_material": "PLA",
                "filament_vendor_name": "Bambu Lab",
                "filament_extra_profile_name": "Bambu PLA Basic",
                "location": "Shelf",
                "extra_sealed": False,
            },
        ]
        tray = {
            "tray_uuid": "uuid-missing-in-spoolman",
            "color": "#112233",
            "type": "PLA",
            "name": "Bambu PLA Basic",
        }
        result = match_tray_to_spool(tray, spools)
        self.assertTrue(result["success"])
        self.assertEqual(result["spool_id"], 202)

    def test_invalid_uuid_all_zeroes_uses_non_bambu_path(self):
        tray = {
            "tray_uuid": "00000000000000000000000000000000",
            "color": "#ff0000",
            "type": "PLA",
            "name": "Any",
        }
        result = match_tray_to_spool(tray, self.base_spools)
        self.assertTrue(result["success"])
        # non-Bambu candidates are 102 (Shelf) and 104 (AMS), AMS preference applies
        self.assertEqual(result["spool_id"], 104)
        self.assertEqual(result["match_strategy"], "color_type_ams_preference")

    def test_uuid_miss_bambu_path_does_not_match_non_bambu(self):
        spools = [
            {
                "id": 301,
                "extra_spool_uuid": "",
                "filament_color_hex": "#AABBCC",
                "filament_material": "PLA",
                "filament_vendor_name": "Polymaker",
                "filament_extra_profile_name": "",
                "location": "AMS",
                "extra_sealed": False,
            }
        ]
        tray = {
            "tray_uuid": "bambu-uuid-not-in-spoolman",
            "color": "#AABBCC",
            "type": "PLA",
            "name": "Bambu PLA Basic",
        }
        result = match_tray_to_spool(tray, spools)
        self.assertFalse(result["success"])
        self.assertIn("No unsealed Bambu spool matched UUID", result["reason"])

    def test_color_alpha_is_normalized(self):
        tray = {
            "tray_uuid": "",
            "color": "#FF0000FF",
            "type": "PETG",
            "name": "Any",
        }
        result = match_tray_to_spool(tray, self.base_spools)
        self.assertTrue(result["success"])
        self.assertEqual(result["spool_id"], 103)

    def test_bambu_profile_name_matches_when_spool_profile_is_quoted(self):
        spools = [
            {
                "id": 501,
                "extra_spool_uuid": "",
                "filament_color_hex": "#000000",
                "filament_material": "PLA",
                "filament_vendor_name": "Bambu Lab",
                "filament_extra_profile_name": '"Bambu PLA Matte"',
                "location": "AMS 2",
                "extra_sealed": False,
            },
            {
                "id": 502,
                "extra_spool_uuid": "",
                "filament_color_hex": "#000000",
                "filament_material": "PLA",
                "filament_vendor_name": "Bambu Lab",
                "filament_extra_profile_name": '"Bambu PLA Matte"',
                "location": "Shelf",
                "extra_sealed": True,
            },
        ]
        tray = {
            "tray_uuid": "CFF35EB1828546EDBB1A2C3BD194952D",
            "color": "#000000FF",
            "type": "PLA",
            "name": "Bambu PLA Matte",
        }
        result = match_tray_to_spool(tray, spools)
        self.assertTrue(result["success"])
        self.assertEqual(result["spool_id"], 501)

    def test_multiple_non_bambu_none_in_ams_is_error(self):
        spools = [
            {
                "id": 401,
                "extra_spool_uuid": "",
                "filament_color_hex": "#445566",
                "filament_material": "PLA",
                "filament_vendor_name": "Polymaker",
                "filament_extra_profile_name": "",
                "location": "Shelf",
                "extra_sealed": False,
            },
            {
                "id": 402,
                "extra_spool_uuid": "",
                "filament_color_hex": "#445566",
                "filament_material": "PLA",
                "filament_vendor_name": "eSUN",
                "filament_extra_profile_name": "",
                "location": "Drawer",
                "extra_sealed": False,
            },
        ]
        tray = {
            "tray_uuid": "",
            "color": "#445566",
            "type": "PLA",
            "name": "Any",
        }
        result = match_tray_to_spool(tray, spools)
        self.assertFalse(result["success"])
        self.assertIn("none in AMS", result["reason"])

    def test_multicolor_first_hex_matches_when_single_color_missing(self):
        spools = [
            {
                "id": 601,
                "extra_spool_uuid": "",
                "filament_color_hex": "",
                "filament_multi_color_hexes": "ffa11f,ff5900",
                "filament_material": "PLA",
                "filament_vendor_name": "Polymaker",
                "filament_extra_profile_name": "",
                "location": "Shelf",
                "extra_sealed": False,
            }
        ]
        tray = {
            "tray_uuid": "",
            "color": "#FFA11F",
            "type": "PLA",
            "name": "Any",
        }
        result = match_tray_to_spool(tray, spools)
        self.assertTrue(result["success"])
        self.assertEqual(result["spool_id"], 601)
        self.assertEqual(result["match_strategy"], "multicolor_first_hex")

    def test_multicolor_any_hex_matches_when_first_hex_misses(self):
        spools = [
            {
                "id": 602,
                "extra_spool_uuid": "",
                "filament_color_hex": "",
                "filament_multi_color_hexes": "982abc,e63b7a,00a1d8",
                "filament_material": "PLA",
                "filament_vendor_name": "eSUN",
                "filament_extra_profile_name": "",
                "location": "AMS",
                "extra_sealed": False,
            }
        ]
        tray = {
            "tray_uuid": "",
            "color": "#00A1D8",
            "type": "PLA",
            "name": "Any",
        }
        result = match_tray_to_spool(tray, spools)
        self.assertTrue(result["success"])
        self.assertEqual(result["spool_id"], 602)
        self.assertEqual(result["match_strategy"], "multicolor_any_hex")

    def test_multicolor_first_hex_uses_ams_preference_when_multiple(self):
        spools = [
            {
                "id": 603,
                "extra_spool_uuid": "",
                "filament_color_hex": "",
                "filament_multi_color_hexes": "e292fe,fff994,6ef785,93e3fd",
                "filament_material": "PLA",
                "filament_vendor_name": "Polymaker",
                "filament_extra_profile_name": "",
                "location": "Shelf",
                "extra_sealed": False,
            },
            {
                "id": 604,
                "extra_spool_uuid": "",
                "filament_color_hex": "",
                "filament_multi_color_hexes": "e292fe,000000",
                "filament_material": "PLA",
                "filament_vendor_name": "eSUN",
                "filament_extra_profile_name": "",
                "location": "AMS",
                "extra_sealed": False,
            },
        ]
        tray = {
            "tray_uuid": "",
            "color": "#E292FE",
            "type": "PLA",
            "name": "Any",
        }
        result = match_tray_to_spool(tray, spools)
        self.assertTrue(result["success"])
        self.assertEqual(result["spool_id"], 604)
        self.assertEqual(result["match_strategy"], "multicolor_first_hex_ams_preference")

    def test_external_spool_bambu_profile_no_uuid_matches_bambu_vendor(self):
        """Issue #691: External spool with Bambu profile name but empty UUID
        should still match Bambu Lab vendor spools via color+type+profile."""
        spools = [
            {
                "id": 91,
                "extra_spool_uuid": "2D1BFD3DDC524897BE5BEFA915FE6BA8",
                "filament_color_hex": "#E8DBB7",
                "filament_material": "PLA",
                "filament_vendor_name": "Bambu Lab",
                "filament_extra_profile_name": '"Bambu PLA Matte"',
                "location": "Closet Shelf 4",
                "extra_sealed": False,
            },
            {
                "id": 200,
                "extra_spool_uuid": "",
                "filament_color_hex": "#E8DBB7",
                "filament_material": "PLA",
                "filament_vendor_name": "Polymaker",
                "filament_extra_profile_name": "",
                "location": "Shelf",
                "extra_sealed": False,
            },
        ]
        tray = {
            "tray_uuid": "00000000000000000000000000000000",
            "color": "#E8DBB7FF",
            "type": "PLA",
            "name": "Bambu PLA Matte",
        }
        result = match_tray_to_spool(tray, spools)
        self.assertTrue(result["success"])
        self.assertEqual(result["spool_id"], 91)
        self.assertEqual(result["match_strategy"], "color_type")

    def test_single_color_tier_precedes_multicolor_tiers(self):
        spools = [
            {
                "id": 605,
                "extra_spool_uuid": "",
                "filament_color_hex": "#445566",
                "filament_multi_color_hexes": "",
                "filament_material": "PLA",
                "filament_vendor_name": "Polymaker",
                "filament_extra_profile_name": "",
                "location": "Shelf",
                "extra_sealed": False,
            },
            {
                "id": 606,
                "extra_spool_uuid": "",
                "filament_color_hex": "",
                "filament_multi_color_hexes": "111111,445566,999999",
                "filament_material": "PLA",
                "filament_vendor_name": "eSUN",
                "filament_extra_profile_name": "",
                "location": "AMS",
                "extra_sealed": False,
            },
        ]
        tray = {
            "tray_uuid": "",
            "color": "#445566",
            "type": "PLA",
            "name": "Any",
        }
        result = match_tray_to_spool(tray, spools)
        self.assertTrue(result["success"])
        self.assertEqual(result["spool_id"], 605)
        self.assertEqual(result["match_strategy"], "color_type")


if __name__ == "__main__":
    unittest.main()
