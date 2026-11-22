from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build34_r3_eop_evidence import check


def fixture():
    records = []
    for index, (queue, interrupt, ring_id) in enumerate((
        ("gfx", False, 0), ("gfx", True, 0), ("compute", False, 4), ("compute", True, 4),
    )):
        start = 1000 + index * 200
        identity = dict(service_epoch=1, route_epoch=index + 1,
                        gfx_generation=index + 1, compute_generation=index + 6)
        seed, target = 2 * index + 10, 2 * index + 11
        before = dict(identity=identity.copy(), begin_ns=start, end_ns=start + 1,
                      fence=seed, other_fence=7, payload_ok=False)
        first = dict(identity=identity.copy(), begin_ns=start + 50, end_ns=start + 53,
                     fence=target, other_fence=7, payload_ok=True)
        final = dict(first, identity=identity.copy(), begin_ns=start + 99, end_ns=start + 100)
        vector = dict(identity=identity.copy(), seen_ns=start + 40, client_id=0x14,
                      source_id=181, ring_id=ring_id, mes_tagged=False)
        records.append(dict(queue=queue, interrupt=interrupt,
                            recipe_sha256=("a" if queue == "gfx" else "b") * 64,
                            target=target, before=before, first_read=first, final_read=final,
                            start_ns=start, submit_ns=start + 30, close_ns=start + 100,
                            cleanup_end_ns=start + 120, lost=False, overflow=False, fault=False,
                            vectors=[vector] if interrupt else []))
    return records


def verify(records):
    return check(records, observe_budget_ns=100, cleanup_budget_ns=30)


class RouteEvidence(unittest.TestCase):
    def test_control_and_eop_for_both_queues(self):
        self.assertEqual(verify(fixture()), dict(status="consistent-r3-eop-route-records",
                                                hardware_attested=False))

    def test_same_tick_read_and_ring_id_bit_outside_decoded_fields(self):
        records = fixture()
        records[3]["vectors"][0]["ring_id"] = 0x84
        first = records[3]["first_read"]
        first["end_ns"] = first["begin_ns"]
        self.assertIs(verify(records)["hardware_attested"], False)

    def test_incomplete_unordered_and_different_recipe_refuse(self):
        records = fixture()
        for invalid in (records[:3], records + records[:1], [records[1], records[0], *records[2:]]):
            with self.subTest(length=len(invalid)), self.assertRaises(ValueError):
                verify(invalid)
        records[1]["recipe_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "recipes differ"):
            verify(records)

    def test_missing_duplicate_unexpected_and_lost_vectors_refuse(self):
        vector = fixture()[1]["vectors"][0]
        for index, fields in ((0, dict(vectors=[vector])), (1, dict(vectors=[])),
                              (1, dict(vectors=[vector, vector])), (2, dict(lost=True)),
                              (3, dict(overflow=True)), (3, dict(lost=0)), (1, dict(fault=True))):
            with self.subTest(case=index, fields=fields.keys()), self.assertRaises(ValueError):
                records = fixture()
                records[index].update(fields)
                verify(records)

    def test_wrong_source_engine_pipe_queue_and_mes_tag_refuse(self):
        for name, value in (("client_id", 0x12), ("source_id", 180), ("ring_id", 0),
                            ("ring_id", 5), ("ring_id", 8), ("ring_id", 0x14),
                            ("ring_id", 0x104), ("mes_tagged", True), ("mes_tagged", 0)):
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                records = fixture()
                records[3]["vectors"][0][name] = value
                verify(records)

    def test_fence_payload_and_peer_must_match_on_first_read(self):
        for fields in (dict(fence=12), dict(payload_ok=False), dict(payload_ok=1), dict(other_fence=8)):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                records = fixture()
                records[1]["first_read"].update(fields)
                verify(records)
        records = fixture()
        records[1]["before"]["payload_ok"] = True
        with self.assertRaisesRegex(ValueError, "no fresh fence"):
            verify(records)

    def test_stale_identity_in_vector_or_either_queue_read_refuses(self):
        for field in ("service_epoch", "route_epoch", "gfx_generation", "compute_generation"):
            for record_type in ("first_read", "final_read", "vector"):
                with self.subTest(field=field, record_type=record_type), self.assertRaisesRegex(ValueError, "identity|epoch"):
                    records = fixture()
                    case = records[1]
                    record = case["vectors"][0] if record_type == "vector" else case[record_type]
                    record["identity"][field] += 20
                    verify(records)
        records = fixture()
        case = records[3]
        for sample in (case["before"], case["first_read"], case["final_read"], case["vectors"][0]):
            sample["identity"]["service_epoch"] = 2
        with self.assertRaisesRegex(ValueError, "service"):
            verify(records)

    def test_reused_epoch_seed_and_target_refuse(self):
        for field in ("route_epoch", "gfx_generation"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "reused trial"):
                records = fixture()
                case = records[1]
                for sample in (case["before"], case["first_read"], case["final_read"], case["vectors"][0]):
                    sample["identity"][field] = records[0]["before"]["identity"][field]
                verify(records)
        for seed, target in ((12, 12), (10, 13), (12, 11)):
            with self.subTest(seed=seed, target=target), self.assertRaisesRegex(ValueError, "reused fence"):
                records = fixture()
                records[1]["before"]["fence"] = seed
                records[1]["target"] = records[1]["first_read"]["fence"] = target
                verify(records)

    def test_final_read_detects_late_peer_progress_and_fence_regression(self):
        for fields in (dict(fence=12), dict(payload_ok=False), dict(other_fence=8)):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                records = fixture()
                records[1]["final_read"].update(fields)
                verify(records)

    def test_vector_and_read_order_and_window_bounds(self):
        for key, location, value in (("seen_ns", "vector", 1230), ("seen_ns", "vector", 1250),
                                     ("end_ns", "before", 1230), ("end_ns", "first_read", 1299),
                                     ("end_ns", "final_read", 1301),
                                     ("close_ns", "case", 1299), ("cleanup_end_ns", "case", 1331),
                                     ("start_ns", "case", 1120)):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                records = fixture()
                case = records[1]
                locations = dict(case=case, vector=case["vectors"][0], before=case["before"],
                                 first_read=case["first_read"], final_read=case["final_read"])
                record = locations[location]
                record[key] = value
                verify(records)

    def test_invalid_deadline_scope_or_raw_fields_refuse(self):
        for budget in (0, True, (1 << 64) - 2):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                check(fixture(), observe_budget_ns=budget, cleanup_budget_ns=30)
        records = fixture()
        records[1]["vectors"][0]["raw_words"] = []
        with self.assertRaisesRegex(ValueError, "unexpected IH vector fields"):
            verify(records)


if __name__ == "__main__":
    unittest.main()
