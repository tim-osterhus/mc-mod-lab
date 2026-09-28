import copy
import unittest

import hud_trace


class HudTraceTests(unittest.TestCase):
    positive_target = {"dimension": "minecraft:overworld", "x": 1, "y": 64, "z": 3,
                       "blockId": "aura:aura_node"}

    def clock_brackets(self):
        return {"start_request_ns": 100_000_000, "start_ack_ns": 200_000_000,
                "stop_request_ns": 10_300_000_000, "stop_ack_ns": 10_400_000_000}

    def server_sample(self, tick, request_ns, response_ns):
        return {
            "serverTick": tick,
            "requestElapsedNanos": request_ns,
            "elapsedNanos": response_ns,
            "snapshot": {
                "serverAuthoritative": True,
                "stateSource": "integrated_server_block_entity",
                "serverTick": tick,
                "blockId": "aura:aura_node",
                "x": 1,
                "y": 64,
                "z": 3,
            },
        }

    def fixture(self, *, mode="positive", target=True):
        start_sequence = 40
        frames = []
        for index in range(21):
            target_record = ({"dimension": "minecraft:overworld", "x": 1, "y": 64, "z": 3,
                              "blockId": "aura:aura_node", "clientWhiteAura": 0,
                              "whiteLayoutCandidate": True} if target else None)
            frames.append({
                "sequence": start_sequence + index + 1,
                "elapsedNanos": index * 500_000_000,
                "clientWorldTick": 100 + index * 10,
                "framebufferWidth": 1280,
                "framebufferHeight": 720,
                "guiWidth": 640,
                "guiHeight": 360,
                "language": "en_us",
                "screenOpen": False,
                "hideGui": False,
                "debugVisible": False,
                "target": target_record,
                "panelRoi": {"x": 0, "y": 0, "width": 640, "height": 352,
                             "whiteCandidatePixels": 0, "rgbSha256": "a" * 64},
                "valueRoi": {"x": 128, "y": 32, "width": 192, "height": 18,
                             "whiteCandidatePixels": 0, "rgbSha256": "b" * 64},
            })
        batch = {
            "traceId": "trace-1", "active": False, "reason": "stopped",
            "startSequence": start_sequence, "elapsedNanos": 10_100_000_000,
            "frameCount": len(frames), "keyframeSequences": [41, 61], "frames": frames,
        }
        server_samples = [
            self.server_sample(100, 0, 100_000_000),
            self.server_sample(302, 10_400_000_000, 10_500_000_000),
        ]
        return [batch], server_samples

    def validate(self, batches=None, samples=None, **kwargs):
        if batches is None or samples is None:
            fixture_batches, fixture_samples = self.fixture()
            batches = fixture_batches if batches is None else batches
            samples = fixture_samples if samples is None else samples
        kwargs.setdefault("python_clock_brackets", self.clock_brackets())
        return hud_trace.validate_trace(batches, server_samples=samples, **kwargs)

    def test_complete_capture_reports_coverage_not_visual_pass(self):
        batches, samples = self.fixture()
        for index, frame in enumerate(batches[0]["frames"]):
            frame["valueRoi"]["whiteCandidatePixels"] = index
            frame["valueRoi"]["rgbSha256"] = f"{index + 1:064x}"
            frame["panelRoi"]["whiteCandidatePixels"] = index * 2
            frame["panelRoi"]["rgbSha256"] = f"{index + 100:064x}"
            frame["target"]["clientWhiteAura"] = index
        result = self.validate(batches, samples, expected_target=self.positive_target)
        self.assertEqual(result["capture_status"], "complete")
        self.assertEqual(result["visual_status"], "unreviewed")
        self.assertEqual(result["pixel_metrics"], "recorded_not_interpreted")
        low, high = result["server_ticks"]["ticks_per_second_bounds"]
        self.assertGreaterEqual(low, 18.0)
        self.assertLessEqual(high, 22.0)
        self.assertEqual(result["server_ticks"]["accepted_ticks_per_second"], [18.0, 22.0])

    def test_saved_capture_requires_complete_transition_pairs_when_requested(self):
        batches, samples = self.fixture()
        batch = batches[0]
        for frame in batch["frames"][10:]:
            frame["target"]["clientWhiteAura"] = 100
        capture = {"metadata": {k: v for k, v in batch.items() if k != "frames"},
                   "frames": batch["frames"], "server_samples": samples,
                   "python_clock_brackets": self.clock_brackets(),
                   "keyframes": [{"sequence": seq} for seq in batch["keyframeSequences"]]}
        with self.assertRaisesRegex(ValueError, "adjacent"):
            hud_trace.validate_capture(capture, require_value_transitions=True)
        capture["metadata"]["keyframeSequences"] = [41, 50, 51, 61]
        capture["keyframes"] = [{"sequence": seq} for seq in [41, 50, 51, 61]]
        result = hud_trace.validate_capture(capture, require_value_transitions=True)
        self.assertEqual((result["value_changes"], result["retained_value_pairs"]), (1, 1))
        self.assertEqual(result["visual_status"], "unreviewed")
        capture["keyframes"].pop()
        with self.assertRaisesRegex(ValueError, "recorder index"):
            hud_trace.validate_capture(capture)

    def test_control_modes_do_not_require_positive_client_aura(self):
        batches, samples = self.fixture()
        result = self.validate(batches, samples, mode="seeded_zero")
        self.assertEqual(result["visual_status"], "unreviewed")

        batches, samples = self.fixture(target=False)
        result = self.validate(batches, samples, mode="lookaway", expected_target=self.positive_target)
        self.assertEqual(result["mode"], "lookaway")
        self.assertIsNone(result["target_identity"])

    def test_other_node_must_differ_from_positive_target(self):
        batches, samples = self.fixture()
        expected = {"dimension": "minecraft:overworld", "x": 9, "y": 64, "z": 3,
                    "blockId": "aura:aura_node"}
        self.assertEqual(self.validate(batches, samples, mode="other_node",
                                       expected_target=expected)["mode"], "other_node")
        expected["x"] = 1
        with self.assertRaisesRegex(ValueError, "still targets"):
            self.validate(batches, samples, mode="other_node", expected_target=expected)

    def test_duplicate_missing_and_wrong_first_sequences_reject(self):
        mutations = (
            lambda f: f[5].update(sequence=f[4]["sequence"]),
            lambda f: f[5].update(sequence=f[5]["sequence"] + 1),
            lambda f: f[0].update(sequence=f[0]["sequence"] + 1),
        )
        for mutate in mutations:
            batches, samples = self.fixture()
            mutate(batches[0]["frames"])
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.validate(batches, samples)

    def test_elapsed_time_gaps_and_stale_final_frame_reject(self):
        cases = (
            lambda b: b[0]["frames"][4].update(elapsedNanos=b[0]["frames"][3]["elapsedNanos"]),
            lambda b: b[0]["frames"][5].update(elapsedNanos=3_000_000_000),
            lambda b: b[0].update(elapsedNanos=10_800_000_000),
            lambda b: b[0].update(elapsedNanos=9_900_000_000),
        )
        for mutate in cases:
            batches, samples = self.fixture()
            mutate(batches)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.validate(batches, samples)

    def test_incomplete_or_badly_stopped_traces_reject(self):
        mutations = (
            lambda b: b[0].update(active=True),
            lambda b: b[0].update(reason="frame_limit"),
            lambda b: b[0].update(reason="inconclusive"),
            lambda b: b[0].update(failure="capture_failed:IllegalStateException"),
            lambda b: b[0].update(frameCount=b[0]["frameCount"] + 1),
            lambda b: b[0]["frames"].pop(8),
            lambda b: b[0].update(frames=[]),
        )
        for mutate in mutations:
            batches, samples = self.fixture()
            mutate(batches)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.validate(batches, samples)

    def test_batches_must_keep_trace_identity_and_order(self):
        batches, samples = self.fixture()
        first = copy.deepcopy(batches[0])
        first.update(active=True, reason="recording", elapsedNanos=5_000_000_000,
                     frameCount=10, keyframeSequences=[41], frames=first["frames"][:10])
        final = copy.deepcopy(batches[0])
        final["frames"] = final["frames"][10:]
        with self.assertRaisesRegex(ValueError, "identity"):
            other = copy.deepcopy(final)
            other["traceId"] = "other"
            self.validate([first, other], samples)
        result = self.validate([first, final], samples)
        self.assertEqual(result["frame_count"], 21)

    def test_inactive_pagination_accepts_stable_headers_and_empty_tail(self):
        batches, samples = self.fixture()
        complete = batches[0]
        pages = []
        for chunk in (complete["frames"][:10], complete["frames"][10:], []):
            page = copy.deepcopy(complete)
            page["frames"] = chunk
            pages.append(page)
        result = self.validate(pages, samples)
        self.assertEqual(result["frame_count"], 21)

    def test_inactive_pagination_rejects_reactivation_and_header_change(self):
        for change in ("reactivate", "elapsedNanos", "frameCount", "keyframeSequences"):
            batches, samples = self.fixture()
            complete = batches[0]
            first = copy.deepcopy(complete)
            first["frames"] = complete["frames"][:10]
            last = copy.deepcopy(complete)
            last["frames"] = complete["frames"][10:]
            if change == "reactivate":
                last["active"] = True
                last["reason"] = "recording"
            elif change == "keyframeSequences":
                last["keyframeSequences"] = [41]
            else:
                last[change] += 1
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.validate([first, last], samples)

    def test_nonmonotonic_server_samples_and_abnormal_tps_reject(self):
        cases = (
            lambda s: s[1].update(serverTick=True),
            lambda s: s[1].update(serverTick=s[0]["serverTick"]),
            lambda s: s[1]["snapshot"].update(serverAuthoritative=False),
            lambda s: s[1]["snapshot"].update(stateSource="client_world_block_entity_cache"),
            lambda s: s[1]["snapshot"].update(serverTick=True),
            lambda s: s[1]["snapshot"].update(serverTick=301),
            lambda s: s[0].update(elapsedNanos=100_000_001),
            lambda s: s[1].update(requestElapsedNanos=10_399_999_999),
            lambda s: s[1].update(requestElapsedNanos=20_000_000_000,
                                  elapsedNanos=22_000_000_000),
        )
        for mutate in cases:
            batches, samples = self.fixture()
            mutate(samples)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.validate(batches, samples)

    def test_positive_expected_target_must_match_authoritative_snapshot(self):
        batches, samples = self.fixture()
        samples[1]["snapshot"]["x"] = 2
        with self.assertRaisesRegex(ValueError, "expected_target"):
            self.validate(batches, samples, expected_target=self.positive_target)

    def test_before_and_after_server_samples_must_name_the_same_block(self):
        batches, samples = self.fixture()
        samples[1]["snapshot"]["x"] = 2
        with self.assertRaisesRegex(ValueError, "changed block identity"):
            self.validate(batches, samples)

    def test_request_brackets_bound_capture_without_clock_origin_alignment(self):
        batches, samples = self.fixture()
        result = self.validate(batches, samples)
        self.assertEqual(result["visual_status"], "unreviewed")
        brackets = self.clock_brackets()
        brackets["start_ack_ns"] = 500_000_000
        with self.assertRaisesRegex(ValueError, "required capture duration"):
            self.validate(batches, samples, python_clock_brackets=brackets)
        brackets = self.clock_brackets()
        brackets["start_ack_ns"] = brackets["start_request_ns"]
        with self.assertRaisesRegex(ValueError, "Java trace duration"):
            self.validate(batches, samples, python_clock_brackets=brackets)

    def test_client_world_ticks_do_not_supply_server_rate_evidence(self):
        batches, samples = self.fixture()
        batches[0]["frames"][-1]["clientWorldTick"] = 0
        result = self.validate(batches, samples)
        self.assertEqual(result["capture_status"], "complete")
        self.assertEqual(result["server_ticks"]["delta"], 202)

    def test_invalid_boolean_numbers_bounds_and_roi_clipping_reject(self):
        cases = (
            lambda b: b[0]["frames"][0].update(sequence=True),
            lambda b: b[0]["frames"][0].update(elapsedNanos=float("nan")),
            lambda b: b[0]["frames"][0].update(screenOpen=0),
            lambda b: b[0]["frames"][0].update(framebufferWidth=2048),
            lambda b: b[0]["frames"][0]["panelRoi"].update(x=1),
            lambda b: b[0]["frames"][0]["valueRoi"].update(x=129),
            lambda b: b[0]["frames"][0]["valueRoi"].update(x=1200),
            lambda b: b[0]["frames"][0]["valueRoi"].update(whiteCandidatePixels=True),
            lambda b: b[0]["frames"][0]["panelRoi"].update(rgbSha256="bad"),
        )
        for mutate in cases:
            batches, samples = self.fixture()
            mutate(batches)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.validate(batches, samples)

    def test_positive_fixed_view_and_english_hud_flags_are_required(self):
        for field, value in (("language", "fr_fr"), ("hideGui", True),
                             ("debugVisible", True), ("screenOpen", True)):
            batches, samples = self.fixture()
            batches[0]["frames"][4][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.validate(batches, samples)
        batches, samples = self.fixture()
        batches[0]["frames"][4]["target"]["x"] += 1
        with self.assertRaisesRegex(ValueError, "target identity changed"):
            self.validate(batches, samples)


if __name__ == "__main__":
    unittest.main()
