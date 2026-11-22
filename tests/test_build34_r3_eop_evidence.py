from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build34_r3_eop_evidence import check, check_ih_capture


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


def capture_fixture(ring_size=128, cursor=96):
    records = fixture()
    for case in records:
        normalized = case.pop("vectors")
        start = case["start_ns"]
        identity = case["before"]["identity"]
        batches = []

        def batch(begin, end, read, write, *entries):
            batches.append(dict(identity=identity.copy(), begin_ns=start + begin, end_ns=start + end,
                                read_cursor=read, writeback_before=write, writeback_after=write,
                                entries=list(entries)))

        batch(2, 3, cursor, cursor)
        end_cursor = cursor
        if normalized:
            ring_id = normalized[0]["ring_id"]
            entry = bytes((0x14, 0xB5, ring_id, 0x80)) + bytes(28)
            end_cursor = (cursor + len(entry)) % ring_size
            batch(37, 40, cursor, end_cursor, entry)
        batch(105, 109, end_cursor, end_cursor)
        case["ih_capture"] = batches
    return records


def verify_capture(records, ring_size=128):
    return check_ih_capture(records, ring_size_bytes=ring_size, observe_budget_ns=100, cleanup_budget_ns=30)


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


class RawIHCapture(unittest.TestCase):
    def test_gfx_compute_wrap_and_nonwrap_preserve_normalized_result(self):
        for ring_size, offset in ((128, 96), (128, 32), (64, 32), (262144, 262112)):
            with self.subTest(ring_size=ring_size, offset=offset):
                records = capture_fixture(ring_size, offset)
                result = verify_capture(records, ring_size)
                self.assertEqual(result, dict(verify(fixture()), raw_ih_capture_checked=True))
                self.assertNotIn("vectors", records[1])
                self.assertEqual(len(records[1]["ih_capture"][1]["entries"][0]), 32)

    def test_header_layout_and_mes_tag_not_confused_with_ring_or_vmid_bits(self):
        records = capture_fixture()
        entry = records[3]["ih_capture"][1]["entries"]
        tagged = bytearray(entry[0])
        tagged[2] |= 0x80
        tagged[3] |= 1
        tagged[20] = 1
        tagged[23] = 1
        entry[0] = bytes(tagged)
        self.assertIs(verify_capture(records)["hardware_attested"], False)
        tagged[19] = 1
        entry[0] = bytes(tagged)
        with self.assertRaisesRegex(ValueError, "not the expected legacy CP EOP"):
            verify_capture(records)

    def test_bad_entry_length_type_byte_order_and_routing_refused(self):
        original = capture_fixture()[3]["ih_capture"][1]["entries"][0]
        for invalid in (original[:31], original + b"\0", bytearray(original), original[:4][::-1] + original[4:],
                        bytes((0x14, 0xB5, 0x05, 0)) + original[4:], bytes((0x14, 0xB4, 4, 0)) + original[4:]):
            with self.subTest(kind=type(invalid), length=len(invalid)), self.assertRaises(ValueError):
                records = capture_fixture()
                records[3]["ih_capture"][1]["entries"][0] = invalid
                verify_capture(records)

    def test_refuses_overflow_full_and_unsafe_geometry_from_either_writeback(self):
        for field in ("writeback_before", "writeback_after"):
            for bit in (1, 0x40000, 0x80000):
                with self.subTest(field=field, bit=bit), self.assertRaisesRegex(ValueError, "overflow or insufficient"):
                    records = capture_fixture()
                    records[1]["ih_capture"][1][field] |= bit
                    verify_capture(records)
        for size in (0, 32, 96, 262145, True):
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, "ring size"):
                verify_capture(capture_fixture(), size)
        for field, value in (("read_cursor", 4), ("read_cursor", 128), ("writeback_before", 0x100000),
                             ("writeback_after", True)):
            with self.subTest(field=field, value=value), self.assertRaisesRegex(ValueError, "cursor"):
                records = capture_fixture()
                records[1]["ih_capture"][1][field] = value
                verify_capture(records)

    def test_refuses_unstable_writeback_omissions_duplicate_and_skipped_cursor(self):
        for fields, message in ((dict(writeback_after=32), "changed during capture"),
                                (dict(entries=[]), "entry count"),
                                (dict(read_cursor=64), "skipped or replayed")):
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, message):
                records = capture_fixture()
                records[1]["ih_capture"][1].update(fields)
                verify_capture(records)
        records = capture_fixture()
        target = records[1]["ih_capture"][1]
        target["entries"].append(target["entries"][0])
        target["writeback_before"] = target["writeback_after"] = 32
        with self.assertRaisesRegex(ValueError, "unexpected IH traffic"):
            verify_capture(records)

    def test_rejects_early_late_and_stale_batch_and_missing_bookends(self):
        for index, fields, message in (
            (0, dict(end_ns=1230), "begin empty before"),
            (1, dict(begin_ns=1230), "outside the single-entry trial"),
            (1, dict(end_ns=1250), "submit-to-read window"),
            (2, dict(begin_ns=1299), "end empty during cleanup"),
            (2, dict(end_ns=1321), "invalid IH batch end"),
        ):
            with self.subTest(index=index, fields=fields), self.assertRaisesRegex(ValueError, message):
                records = capture_fixture()
                records[1]["ih_capture"][index].update(fields)
                verify_capture(records)
        records = capture_fixture()
        records[1]["ih_capture"][1]["identity"]["compute_generation"] += 1
        with self.assertRaisesRegex(ValueError, "crossed a service, route or queue epoch"):
            verify_capture(records)
        for length in (0, 1, 65):
            with self.subTest(length=length), self.assertRaisesRegex(ValueError, "bounded, bracketed"):
                records = capture_fixture()
                records[0]["ih_capture"] = records[0]["ih_capture"][:1] * length
                verify_capture(records)

    def test_retains_no_interrupt_control_and_first_fence_checks(self):
        records = capture_fixture()
        reference = records[1]["ih_capture"][1]
        unexpected = dict(reference, identity=records[0]["before"]["identity"], begin_ns=1037, end_ns=1040)
        records[0]["ih_capture"].insert(1, unexpected)
        final = records[0]["ih_capture"][-1]
        final.update(read_cursor=0, writeback_before=0, writeback_after=0)
        with self.assertRaisesRegex(ValueError, "unexpected IH observations"):
            verify_capture(records)
        records = capture_fixture()
        records[1]["first_read"]["payload_ok"] = False
        with self.assertRaisesRegex(ValueError, "no fresh fence and verified payload"):
            verify_capture(records)


if __name__ == "__main__":
    unittest.main()
