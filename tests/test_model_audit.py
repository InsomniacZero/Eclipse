"""Deterministic tests for Gemini Web model audit parsing and classification."""
import json
import unittest

from eclipse.model_audit import (
    build_variant_owners,
    extract_gemini_access_token,
    classify_variant,
    compare_selection,
    enrich_model_diagnostics,
    extract_rpc_payloads,
    observed_turn,
    parse_batchexecute_frames,
)


def _frame(value):
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    utf16_length = len(text.encode("utf-16-le")) // 2
    return ")]}'\n" + str(utf16_length) + "\n" + text + "\n"


class ModelAuditParsingTests(unittest.TestCase):
    def test_extracts_primary_snlm0e_token(self):
        self.assertEqual(
            extract_gemini_access_token('{"SNlM0e":"primary-token"}'),
            "primary-token",
        )

    def test_falls_back_to_alternate_thykhd_token_with_spacing(self):
        html = '{"cfb2h":"build","thykhd" : "alternate-token","FdrFJe":"session"}'
        self.assertEqual(extract_gemini_access_token(html), "alternate-token")

    def test_returns_empty_when_no_supported_token_exists(self):
        self.assertEqual(extract_gemini_access_token('{"cfb2h":"build"}'), "")

    def test_parse_length_prefixed_frame_counts_utf16_code_units(self):
        expected = [["hello 😀"]]
        self.assertEqual(parse_batchexecute_frames(_frame(expected)), [expected])

    def test_parse_raw_json_for_fixture(self):
        expected = {"ok": True, "model": "Gemini"}
        self.assertEqual(parse_batchexecute_frames(json.dumps(expected)), [expected])

    def test_extract_rpc_payload_by_rpc_id(self):
        payload = {"models": ["model-a"]}
        frame = [[["wrb.fr", "otAQ7b", json.dumps(payload), None]]]
        self.assertEqual(extract_rpc_payloads(_frame(frame), "otAQ7b"), [payload])
        self.assertEqual(extract_rpc_payloads(_frame(frame), "hNvQHb"), [])

    def test_variant_owner_maps_model_id_and_listed_variant(self):
        row = ["9d8ca3786ebdfbea", "Pro"]
        row.extend([None] * 4)
        row.append(["e6fa609c3fa255c0"])
        row.extend([None] * 4)
        row.append("Gemini Pro")
        body = [None] * 15 + [[row]]
        owners = build_variant_owners(body)
        self.assertEqual(owners["9d8ca3786ebdfbea"][0]["name"], "Gemini Pro")
        self.assertEqual(owners["e6fa609c3fa255c0"][0]["name"], "Gemini Pro")

    def test_compare_reports_missing_header_as_unverified(self):
        self.assertEqual(compare_selection("abcd", "abcd", [], {}, False), "unverified")

    def test_compare_reports_exact_variant_match(self):
        self.assertEqual(compare_selection("abcdef0123456789", "ABCDEF0123456789", [], {}, True), "variant_id_match")

    def test_compare_detects_cross_bucket_mismatch(self):
        expected = [{"model_id": "pro-id", "name": "Gemini Pro"}]
        observed = {"model_names": ["Gemini Flash"]}
        self.assertEqual(compare_selection("a" * 16, "b" * 16, expected, observed, True), "bucket_mismatch")

    def test_compare_does_not_guess_when_labels_ambiguous(self):
        expected = [{"model_id": "pro-id", "name": "Gemini Pro"}]
        observed = {"model_names": ["Gemini Flash", "Gemini Flash Thinking"]}
        self.assertEqual(compare_selection("a" * 16, "b" * 16, expected, observed, True), "ambiguous")

    def test_observed_turn_requires_response_id_match_when_available(self):
        turns = [[[None, "old-rid"]], [[None, "new-rid"]]]
        turn, status = observed_turn(turns, "new-rid")
        self.assertEqual(turn, turns[1])
        self.assertEqual(status, "response_id_match")
        turn, status = observed_turn(turns, "missing-rid")
        self.assertIsNone(turn)
        self.assertEqual(status, "response_id_not_found")

    def test_thought_metadata_disambiguates_shared_bucket(self):
        candidate = [None] * 38
        candidate[37] = [["thinking trace"]]
        turn = [None, None, None, [[candidate]]]
        owners = {
            "abcdef0123456789": [
                {"model_id": "fast", "name": "Gemini Flash"},
                {"model_id": "thinking", "name": "Gemini Flash Thinking"},
            ]
        }
        result = classify_variant("abcdef0123456789", turn, owners)
        self.assertTrue(result["has_thoughts_metadata"])
        self.assertEqual(result["model_names"], ["Gemini Flash Thinking"])


class ModelAuditAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_conversation_id_is_unverified_without_network(self):
        diagnostics = {"requested_model": "gemini-3.1-pro"}
        await enrich_model_diagnostics(
            diagnostics,
            cookie="",
            access_token="",
            build_label="",
            session_id="",
            selection_hash=None,
        )
        self.assertEqual(diagnostics["identity_verification"], "unverified")
        self.assertIn("conversation ID", diagnostics["notes"][0])

    async def test_cookie_present_but_missing_snlm0e_is_not_misreported_as_no_account(self):
        diagnostics = {"conversation_id": "c_test"}
        cookie = "__Secure-1PSID=redacted; SIDCC=redacted"
        await enrich_model_diagnostics(
            diagnostics,
            cookie=cookie,
            access_token="",
            build_label="build",
            session_id="session",
            selection_hash="abcdef0123456789",
        )
        self.assertTrue(diagnostics["cookie_bundle_supplied"])
        self.assertTrue(diagnostics["secure_psid_present"])
        self.assertTrue(diagnostics["session_cookie_cc_present"])
        self.assertFalse(diagnostics["access_token_available"])
        self.assertEqual(diagnostics["identity_verification"], "unverified")
        self.assertIn("SNlM0e", diagnostics["notes"][0])
        self.assertNotIn("An authenticated Gemini Web session is required", diagnostics["notes"][0])


if __name__ == "__main__":
    unittest.main()
