from pathlib import Path
from struct import pack, unpack
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build34_r3_eop_evidence import check, check_ih_capture, check_one_shot_irq_delivery


_BAR0_MC_BASE = 0x1200000000
_BAR0_SIZE = 4096


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
    for index, case in enumerate(records):
        normalized = case.pop("vectors")
        start = case["start_ns"]
        identity = case["before"]["identity"]
        batches = []
        fence_offset = 16 * index
        for name in ("before", "first_read", "final_read"):
            case[name].update(fence_offset=fence_offset, other_fence_offset=fence_offset + 8)
        address = _BAR0_MC_BASE + fence_offset
        control = 0x42000000 if case["interrupt"] else 0x40000000
        case["release_mem"] = pack("<8I", 0xC0064900, 0x06603514, control,
                                   address & 0xFFFFFFFF, address >> 32, case["target"], 0, 0)

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


def verify_capture(records, ring_size=128, *, bar0_base=_BAR0_MC_BASE, bar0_size=_BAR0_SIZE):
    return check_ih_capture(records, ring_size_bytes=ring_size, bar0_mc_base=bar0_base,
                            bar0_size_bytes=bar0_size, observe_budget_ns=100, cleanup_budget_ns=30)


def rewrite_fence_slots(case, offset, peer_offset):
    for name in ("before", "first_read", "final_read"):
        case[name].update(fence_offset=offset, other_fence_offset=peer_offset)
    words = list(unpack("<8I", case["release_mem"]))
    address = _BAR0_MC_BASE + offset
    words[3:5] = [address & 0xFFFFFFFF, address >> 32]
    case["release_mem"] = pack("<8I", *words)


def one_shot_fixture():
    cursor, ring_size = 96, 128
    records = capture_fixture(ring_size, cursor)
    identity = dict(service_epoch=3, route_epoch=5, gfx_generation=7, compute_generation=9)
    scope = dict(identity=identity.copy(), initial_read_cursor=cursor, ring_size_bytes=ring_size,
                 bar0_mc_base=_BAR0_MC_BASE, bar0_size_bytes=_BAR0_SIZE, irq_source_token=28,
                 gfx_fence_offset=16, compute_fence_offset=32, observe_budget_ns=100, cleanup_budget_ns=30,
                 terminal_deadline_ns=1760)
    for index, case in enumerate(records):
        queue = case["queue"]
        is_gfx = queue == "gfx"
        rewrite_fence_slots(case, 16 if is_gfx else 32, 32 if is_gfx else 16)
        for name in ("before", "first_read", "final_read"):
            case[name]["identity"] = identity.copy()
            case[name]["other_fence"] = 7 if is_gfx else records[1]["target"]
        case["isr_dispatches"] = [dict(identity=identity.copy(), source_token=scope["irq_source_token"],
                                       ordinal=1 + index // 2, seen_ns=case["start_ns"] + 34)] if case["interrupt"] else []
        for batch in case["ih_capture"]:
            batch["identity"] = identity.copy()
            batch["read_cursor"] = cursor
            cursor = (cursor + 32 * len(batch["entries"])) % ring_size
            batch["writeback_before"] = batch["writeback_after"] = cursor
    return records, scope


def verify_one_shot(records, scope, **terminal_fields):
    terminal = dict(identity=scope["identity"].copy(), source_token=scope["irq_source_token"],
                    seen_ns=1740, dispatch_count=2)
    terminal.update(terminal_fields)
    return check_one_shot_irq_delivery(records, scope=scope, terminal=terminal)


class OneShotIrqDelivery(unittest.TestCase):
    def test_single_route_wrap_correlates_dispatch_then_copy_then_fence(self):
        records, scope = one_shot_fixture()
        result = verify_one_shot(records, scope)
        self.assertIs(result["single_route_checked"], True)
        self.assertIs(result["isr_dispatch_checked"], True)
        self.assertIs(result["release_mem_checked"], True)
        self.assertIs(result["hardware_attested"], False)
        self.assertIs(result["old_writer_drain_proved"], False)
        self.assertEqual(records[1]["ih_capture"][-1]["read_cursor"], 0)
        self.assertEqual(records[2]["ih_capture"][0]["read_cursor"], 0)
        self.assertEqual(records[3]["ih_capture"][-1]["read_cursor"], 32)

    def test_ih_copy_without_isr_or_irq_in_control_cannot_pass(self):
        for case_index, count in ((0, 1), (1, 0), (3, 2)):
            with self.subTest(case=case_index, dispatches=count), self.assertRaisesRegex(ValueError, "ISR dispatch"):
                records, scope = one_shot_fixture()
                records[case_index]["isr_dispatches"] = records[1]["isr_dispatches"] * count
                verify_one_shot(records, scope)
        _, scope = one_shot_fixture()
        with self.assertRaisesRegex(ValueError, "single-route case"):
            verify_one_shot(capture_fixture(), scope)

    def test_checks_provider_route_identity_and_continuous_dispatch_ordinal(self):
        for fields, message in ((dict(source_token=29), "admitted route or source"),
                                (dict(ordinal=1), "skipped or replayed"),
                                (dict(ordinal=3), "skipped or replayed"),
                                (dict(ordinal=True), "invalid ISR dispatch ordinal")):
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, message):
                records, scope = one_shot_fixture()
                records[3]["isr_dispatches"][0].update(fields)
                verify_one_shot(records, scope)
        for field in ("service_epoch", "route_epoch", "gfx_generation", "compute_generation"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "admitted route or source"):
                records, scope = one_shot_fixture()
                records[1]["isr_dispatches"][0]["identity"][field] += 1
                verify_one_shot(records, scope)

    def test_requires_dispatch_after_submit_and_before_the_vector_copy(self):
        for relative, message in ((30, "invalid ISR dispatch time"), (38, "copy began before"),
                                  (50, "copy began before")):
            with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, message):
                records, scope = one_shot_fixture()
                case = records[3]
                case["isr_dispatches"][0]["seen_ns"] = case["start_ns"] + relative
                verify_one_shot(records, scope)
        records, scope = one_shot_fixture()
        records[3]["first_read"]["begin_ns"] = records[3]["ih_capture"][1]["end_ns"]
        with self.assertRaisesRegex(ValueError, "submit-to-read window"):
            verify_one_shot(records, scope)

    def test_refuses_route_rearm_and_generation_change_between_cases(self):
        for field in ("route_epoch", "gfx_generation", "compute_generation"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "admitted route or queue generation"):
                records, scope = one_shot_fixture()
                case = records[2]
                for sample in (case["before"], case["first_read"], case["final_read"], *case["ih_capture"]):
                    sample["identity"][field] += 1
                verify_one_shot(records, scope)

    def test_refuses_cursor_reset_before_first_window_or_across_wrap(self):
        records, scope = one_shot_fixture()
        scope["initial_read_cursor"] = 64
        with self.assertRaisesRegex(ValueError, "skipped or replayed"):
            verify_one_shot(records, scope)
        records, scope = one_shot_fixture()
        for batch in records[2]["ih_capture"]:
            batch.update(read_cursor=96, writeback_before=96, writeback_after=96)
        with self.assertRaisesRegex(ValueError, "skipped or replayed"):
            verify_one_shot(records, scope)

    def test_refuses_new_self_consistent_packet_to_an_unadmitted_slot(self):
        for offset, peer_offset in ((40, 32), (16, 40), (32, 16)):
            with self.subTest(offset=offset, peer_offset=peer_offset), self.assertRaisesRegex(ValueError, "admitted queue pair"):
                records, scope = one_shot_fixture()
                rewrite_fence_slots(records[1], offset, peer_offset)
                verify_one_shot(records, scope)
        records, scope = one_shot_fixture()
        scope["compute_fence_offset"] = scope["gfx_fence_offset"]
        with self.assertRaisesRegex(ValueError, "invalid admitted BAR0 fence pair"):
            verify_one_shot(records, scope)

    def test_refuses_stable_but_changed_peer_across_windows(self):
        for index in (1, 2, 3):
            with self.subTest(case=index), self.assertRaisesRegex(ValueError, "peer fence changed between"):
                records, scope = one_shot_fixture()
                for name in ("before", "first_read", "final_read"):
                    records[index][name]["other_fence"] += 1
                verify_one_shot(records, scope)

    def test_terminal_counter_detects_unreported_irq_and_requires_bounded_same_route_sample(self):
        records, scope = one_shot_fixture()
        for fields, message in ((dict(dispatch_count=3), "disagrees with the four windows"),
                                (dict(dispatch_count=1), "disagrees with the four windows"),
                                (dict(source_token=29), "crossed the admitted route or source"),
                                (dict(identity=dict(scope["identity"], route_epoch=12)), "crossed the admitted route"),
                                (dict(seen_ns=1719), "invalid terminal sample time"),
                                (dict(seen_ns=1761), "invalid terminal sample time")):
            with self.subTest(fields=fields), self.assertRaisesRegex(ValueError, message):
                verify_one_shot(records, scope, **fields)


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
                self.assertEqual(result, dict(verify(fixture()), raw_ih_capture_checked=True, release_mem_checked=True))
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

    def test_requires_raw_release_bytes_in_little_endian(self):
        packet = capture_fixture()[1]["release_mem"]
        for invalid in (packet[:-1], packet + b"\0", bytearray(packet), pack(">8I", *unpack("<8I", packet))):
            with self.subTest(kind=type(invalid), length=len(invalid)), self.assertRaisesRegex(ValueError, "RELEASE_MEM"):
                records = capture_fixture()
                records[1]["release_mem"] = invalid
                verify_capture(records)
        records = capture_fixture()
        del records[1]["release_mem"]
        with self.assertRaisesRegex(ValueError, "raw route case"):
            verify_capture(records)

    def test_refuses_changed_header_cache_data_mode_and_interrupt_mode(self):
        for case_index, word, mask in ((0, 2, 0x02000000), (1, 2, 0x02000000), (1, 2, 0x03000000),
                                       (3, 2, 0x60000000), (3, 2, 0x00010000), (1, 1, 1 << 25),
                                       (1, 0, 1 << 16), (3, 7, 1)):
            with self.subTest(case=case_index, word=word, mask=mask), self.assertRaisesRegex(ValueError, "control"):
                records = capture_fixture()
                case = records[case_index]
                words = list(unpack("<8I", case["release_mem"]))
                words[word] ^= mask
                case["release_mem"] = pack("<8I", *words)
                verify_capture(records)

    def test_refuses_other_address_or_data_even_when_fence_and_vector_match(self):
        for word, mask, message in ((3, 8, "target"), (4, 1, "target"), (5, 1, "data"), (6, 1, "data")):
            with self.subTest(word=word), self.assertRaisesRegex(ValueError, f"RELEASE_MEM {message}"):
                records = capture_fixture()
                case = records[3]
                words = list(unpack("<8I", case["release_mem"]))
                words[word] ^= mask
                case["release_mem"] = pack("<8I", *words)
                verify_capture(records)

    def test_requires_stable_distinct_aligned_fence_slots_in_bar(self):
        for sample, changes, message in (
            ("first_read", dict(fence_offset=32), "changed during"),
            ("final_read", dict(other_fence_offset=8), "changed during"),
            ("before", dict(other_fence_offset=16), "aliased"),
            ("before", dict(fence_offset=20), "unaligned"),
            ("first_read", dict(fence_offset=_BAR0_SIZE), "invalid fence_offset"),
            ("final_read", dict(other_fence_offset=-8), "invalid other_fence_offset"),
        ):
            with self.subTest(sample=sample, changes=changes), self.assertRaisesRegex(ValueError, message):
                records = capture_fixture()
                records[1][sample].update(changes)
                verify_capture(records)

    def test_rejects_unknown_unaligned_or_overflowing_aperture(self):
        for base, size in ((0, _BAR0_SIZE), (True, _BAR0_SIZE), (_BAR0_MC_BASE + 4, _BAR0_SIZE),
                           (_BAR0_MC_BASE, _BAR0_SIZE - 4), (_BAR0_MC_BASE, 8), ((1 << 64) - 8, 16)):
            with self.subTest(base=base, size=size), self.assertRaisesRegex(ValueError, "BAR0"):
                verify_capture(capture_fixture(), bar0_base=base, bar0_size=size)


if __name__ == "__main__":
    unittest.main()
