import ctypes
import os
import platform
import socket
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import lab


def tcp4(address="127.0.0.1", pid=123, port=9876, state=2, port_bits=0):
    return (struct.pack("<I", state) + socket.inet_aton(address)
            + struct.pack("<IIII", socket.htons(port) | port_bits, 0, 0, pid))


def tcp6(address="::1", pid=123, port=9876, state=2, port_bits=0):
    return struct.pack("<16sII16sIIII", socket.inet_pton(socket.AF_INET6, address), 0,
                       socket.htons(port) | port_bits, bytes(16), 0, 0, state, pid)


def table(*rows, count=None):
    return struct.pack("<I", len(rows) if count is None else count) + b"".join(rows)


class TableApi:
    """Inject bytes independently packed from the documented Windows ABI."""
    def __init__(self, ipv4=(), ipv6=(), replies=None):
        self.tables = {2: table(*ipv4), 23: table(*ipv6)}
        self.replies = replies
        self.calls = []

    def __call__(self, buffer, size_pointer, ordered, family, table_class, reserved):
        if (ordered, family, table_class, reserved) not in ((False, 2, 3, 0), (False, 23, 3, 0)):
            raise AssertionError("unexpected GetExtendedTcpTable arguments")
        size = ctypes.cast(size_pointer, ctypes.POINTER(ctypes.c_uint32)).contents
        capacity = size.value
        self.calls.append((family, buffer is None, capacity))
        if self.replies is not None:
            result, reported_size, data = self.replies[family].pop(0)
        else:
            data = self.tables[family]
            result, reported_size = (122 if buffer is None else 0), len(data)
        if buffer is not None and data:
            if len(data) > capacity:
                raise AssertionError("test data exceeds supplied buffer")
            ctypes.memmove(buffer, data, len(data))
        size.value = reported_size
        return result


class ListeningSocketTests(unittest.TestCase):
    def inspect(self, api, pid=123, port=9876):
        with patch.object(lab.platform, "system", return_value="Windows"), \
             patch.object(lab.ctypes, "WinDLL", return_value=SimpleNamespace(GetExtendedTcpTable=api),
                          create=True) as loader, \
             patch.object(lab.subprocess, "run", side_effect=AssertionError("no subprocess allowed")):
            result = lab.listening_socket(pid, port)
            loader.assert_called_once_with("iphlpapi", use_last_error=True)
            return result

    def test_native_abi_and_binding(self):
        self.assertEqual(ctypes.sizeof(lab._TcpRowOwnerPid), 24)
        self.assertEqual(ctypes.sizeof(lab._Tcp6RowOwnerPid), 56)
        for row_type, offsets in ((lab._TcpRowOwnerPid, (0, 4, 8, 12, 16, 20)),
                                  (lab._Tcp6RowOwnerPid, (0, 16, 20, 24, 40, 44, 48, 52))):
            self.assertEqual(ctypes.alignment(row_type), 4)
            self.assertEqual(tuple(getattr(row_type, name).offset for name, _ in row_type._fields_), offsets)
        api = TableApi(ipv4=[tcp4()])
        self.assertTrue(self.inspect(api))
        self.assertEqual(api.argtypes, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32), ctypes.c_int,
                                       ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32])
        self.assertIs(api.restype, ctypes.c_uint32)
        self.assertEqual(api.calls, [(2, True, 0), (2, False, 28), (23, True, 0), (23, False, 4)])

    def test_strict_single_listener_across_both_families(self):
        cases = [([], []), ([tcp4("0.0.0.0")], []), ([tcp4("192.0.2.1")], []),
                 ([tcp4("127.0.0.2")], []), ([tcp4(pid=0)], []), ([tcp4(pid=456)], []),
                 ([tcp4(pid=0xffffffff)], []), ([tcp4(), tcp4()], []),
                 ([tcp4(), tcp4("0.0.0.0", pid=456)], []), ([], [tcp6()]),
                 ([], [tcp6("::")]), ([], [tcp6("2001:db8::1")]),
                 ([tcp4()], [tcp6()]), ([tcp4()], [tcp6("::")]),
                 ([tcp4()], [tcp6("::ffff:127.0.0.1")]),
                 ([tcp4()], [tcp6("2001:db8::1", pid=456)])]
        for ipv4, ipv6 in cases:
            with self.subTest(ipv4=ipv4, ipv6=ipv6):
                with self.assertRaisesRegex(lab.LabError, "one 127.0.0.1") as error:
                    self.inspect(TableApi(ipv4, ipv6))
                self.assertEqual(error.exception.status, "unsupported")

    def test_other_ports_do_not_count(self):
        self.assertTrue(self.inspect(TableApi([tcp4(), tcp4("0.0.0.0", port=9877)], [tcp6(port=9877)])))

    def test_port_network_byte_order_and_unused_upper_bits(self):
        for port in (1, 80, 9876, 49152, 65535):
            for bits in (0, 0xabcd0000):
                with self.subTest(port=port, upper_bits=bits):
                    self.assertTrue(self.inspect(TableApi([tcp4(port=port, port_bits=bits)]), port=port))
                    with self.assertRaisesRegex(lab.LabError, "one 127.0.0.1"):
                        self.inspect(TableApi([tcp4(port=port)], [tcp6(port=port, port_bits=bits)]), port=port)
        row = bytearray(tcp4())
        row[8:12] = struct.pack("<I", 9876)  # Wrong: host-order port, not network order.
        with self.assertRaisesRegex(lab.LabError, "one 127.0.0.1"):
            self.inspect(TableApi([bytes(row)]))

    def test_resizes_use_reported_size_and_final_count(self):
        for family, row in ((2, tcp4()), (23, tcp6())):
            data = table(row, row)
            api = TableApi(replies={family: [(122, 4, b""), (122, 8, b""),
                                             (122, len(data), b""), (0, len(data), data)]})
            rows = lab._tcp_listener_rows(api, family)
            self.assertEqual(len(rows), 2)
            self.assertEqual([entry.dwOwningPid for entry in rows], [123, 123])
            self.assertEqual(api.calls, [(family, True, 0), (family, False, 4),
                                         (family, False, 8), (family, False, len(data))])

    def test_shrink_and_estimated_size_allow_unused_capacity(self):
        for family, row in ((2, tcp4()), (23, tcp6())):
            data = table(row)
            for reported_size in (len(data), 128):
                api = TableApi(replies={family: [(122, 128, b""), (0, reported_size, data)]})
                self.assertEqual(len(lab._tcp_listener_rows(api, family)), 1)
            api = TableApi(replies={family: [(122, 128, b""), (0, 4, table())]})
            self.assertEqual(lab._tcp_listener_rows(api, family), [])

    def test_sizing_errors_fail_before_allocation(self):
        for family in (2, 23):
            for code in (0, 1, 5, 50, 87, 999):
                with self.subTest(family=family, code=code), \
                     patch.object(lab.ctypes, "create_string_buffer") as allocate:
                    api = TableApi(replies={family: [(code, 28, b"")]})
                    with self.assertRaisesRegex(lab.LabError, "sizing failed"):
                        lab._tcp_listener_rows(api, family)
                    allocate.assert_not_called()
                    self.assertEqual(len(api.calls), 1)

    def test_invalid_sizing_bounds_fail_before_allocation(self):
        for family in (2, 23):
            for size in (0, 3, lab.MAX_TCP_TABLE_BYTES + 1, 0xffffffff):
                with self.subTest(family=family, size=size), \
                     patch.object(lab.ctypes, "create_string_buffer") as allocate:
                    api = TableApi(replies={family: [(122, size, b"")]})
                    with self.assertRaisesRegex(lab.LabError, "size is invalid"):
                        lab._tcp_listener_rows(api, family)
                    allocate.assert_not_called()

    def test_resize_must_grow_within_limit(self):
        for family in (2, 23):
            for size in (0, 3, 4, lab.MAX_TCP_TABLE_BYTES + 1, 0xffffffff):
                with self.subTest(family=family, size=size):
                    api = TableApi(replies={family: [(122, 4, b""), (122, size, b"")]})
                    with self.assertRaisesRegex(lab.LabError, "resize is invalid"):
                        lab._tcp_listener_rows(api, family)
                    self.assertEqual(len(api.calls), 2)

    def test_retry_limit_is_four_calls_per_family(self):
        for family in (2, 23):
            api = TableApi(replies={family: [(122, size, b"") for size in (4, 8, 16, 32)]})
            with self.assertRaisesRegex(lab.LabError, "retry limit"):
                lab._tcp_listener_rows(api, family)
            self.assertEqual(len(api.calls), 4)

    def test_success_size_must_fit_header_and_allocation(self):
        for family, row in ((2, tcp4()), (23, tcp6())):
            data = table(row)
            for size in (0, 3, len(data) + 1, 0xffffffff):
                with self.subTest(family=family, size=size):
                    api = TableApi(replies={family: [(122, len(data), b""), (0, size, data)]})
                    with self.assertRaisesRegex(lab.LabError, "invalid size"):
                        lab._tcp_listener_rows(api, family)

    def test_counts_and_truncated_rows_fail_closed(self):
        for family, row in ((2, tcp4()), (23, tcp6())):
            for data, size in ((table(row), 4), (table(row), 4 + len(row) - 1),
                               (table(row)[:-1], 4 + len(row) - 1),
                               (table(row, count=2), 4 + len(row)), (table(count=0xffffffff), 4)):
                with self.subTest(family=family, data=data, size=size):
                    api = TableApi(replies={family: [(122, len(data), b""), (0, size, data)]})
                    with self.assertRaisesRegex(lab.LabError, "truncated"):
                        lab._tcp_listener_rows(api, family)

    def test_buffer_cap_is_inclusive_and_count_is_bounded(self):
        api = TableApi(replies={2: [(122, lab.MAX_TCP_TABLE_BYTES, b""), (0, 4, table())]})
        self.assertEqual(lab._tcp_listener_rows(api, 2), [])
        self.assertEqual(api.calls[-1][2], lab.MAX_TCP_TABLE_BYTES)
        for family, row_type in ((2, lab._TcpRowOwnerPid), (23, lab._Tcp6RowOwnerPid)):
            count = (lab.MAX_TCP_TABLE_BYTES - 4) // ctypes.sizeof(row_type) + 1
            api = TableApi(replies={family: [(122, lab.MAX_TCP_TABLE_BYTES, b""),
                                             (0, lab.MAX_TCP_TABLE_BYTES, table(count=count))]})
            with self.assertRaisesRegex(lab.LabError, "truncated"):
                lab._tcp_listener_rows(api, family)

    def test_unexpected_non_listener_states_fail_closed_even_on_other_ports(self):
        for state in (0, 1, 5, 99):
            for ipv4, ipv6 in (([tcp4(), tcp4(port=9877, state=state)], []),
                               ([tcp4()], [tcp6(port=9877, state=state)])):
                with self.subTest(state=state, ipv4=ipv4, ipv6=ipv6):
                    with self.assertRaisesRegex(lab.LabError, "unexpected state"):
                        self.inspect(TableApi(ipv4, ipv6))

    def test_read_errors_in_either_family_prevent_acceptance(self):
        for family in (2, 23):
            for code in (1, 5, 50, 87, 999):
                data = table(tcp4())
                replies = {2: [(122, len(data), b""), (0, len(data), data)],
                           23: [(122, 4, b""), (0, 4, table())]}
                replies[family][-1] = (code, replies[family][-1][1], b"")
                with self.subTest(family=family, code=code):
                    with self.assertRaisesRegex(lab.LabError, f"read failed.*code {code}"):
                        self.inspect(TableApi(replies=replies))

    def test_ipv6_sizing_error_does_not_become_empty_table(self):
        data = table(tcp4())
        api = TableApi(replies={2: [(122, len(data), b""), (0, len(data), data)],
                                23: [(50, 0, b"")]})
        with self.assertRaisesRegex(lab.LabError, "sizing failed.*family 23"):
            self.inspect(api)

    def test_every_check_reads_both_tables_again(self):
        api = TableApi([tcp4()])
        self.assertTrue(self.inspect(api))
        api.tables[23] = table(tcp6())
        with self.assertRaisesRegex(lab.LabError, "one 127.0.0.1"):
            self.inspect(api)
        self.assertEqual([call[0] for call in api.calls], [2, 2, 23, 23] * 2)

    def test_loader_and_native_exceptions_have_no_fallback(self):
        for error in (OSError(5, "access denied"), AttributeError("missing API"), MemoryError()):
            with self.subTest(error=error), \
                 patch.object(lab.platform, "system", return_value="Windows"), \
                 patch.object(lab.ctypes, "WinDLL", side_effect=error, create=True), \
                 patch.object(lab.subprocess, "run") as subprocess:
                with self.assertRaisesRegex(lab.LabError, "could not inspect"):
                    lab.listening_socket(123, 9876)
                subprocess.assert_not_called()
        def failing_api(*args):
            raise OSError(5, "access denied")
        with self.assertRaisesRegex(lab.LabError, "could not inspect"):
            self.inspect(failing_api)

    def test_refusal_blocks_framebuffer_and_screen_http_before_dispatch(self):
        import survival_input
        identity = {"pid": 123, "port": 9876}
        calls = (lambda: survival_input._request_png(identity),
                 lambda: lab.command(identity, "get_screen_buttons"),
                 lambda: lab.status_check(identity))
        for call in calls:
            api = TableApi([tcp4()], [tcp6()])
            with patch.object(lab.platform, "system", return_value="Windows"), \
                 patch.object(lab.ctypes, "WinDLL", return_value=SimpleNamespace(GetExtendedTcpTable=api),
                              create=True), \
                 patch.object(lab, "http_json") as http_json, \
                 patch.object(lab, "urlopen") as urlopen, \
                 patch.object(survival_input.http.client, "HTTPConnection") as connection:
                with self.assertRaisesRegex(lab.LabError, "one 127.0.0.1"):
                    call()
                http_json.assert_not_called()
                urlopen.assert_not_called()
                connection.assert_not_called()

    def test_invalid_pid_and_port_fail_before_native_calls(self):
        for pid, port in ((0, 9876), (-1, 9876), (0x100000000, 9876), (True, 9876),
                          ("123", 9876), (123, 0), (123, 65536), (123, True), (123, "9876")):
            api = TableApi([tcp4()])
            with self.subTest(pid=pid, port=port):
                with self.assertRaisesRegex(lab.LabError, "valid PID and port"):
                    self.inspect(api, pid, port)
                self.assertEqual(api.calls, [])

    def test_non_windows_and_unknown_family_fail_closed(self):
        with patch.object(lab.platform, "system", return_value="Linux"), \
             patch.object(lab.ctypes, "WinDLL", create=True) as loader:
            with self.assertRaisesRegex(lab.LabError, "Windows only"):
                lab.listening_socket(123, 9876)
            loader.assert_not_called()
        api = TableApi()
        with self.assertRaisesRegex(lab.LabError, "address family"):
            lab._tcp_listener_rows(api, 10)
        self.assertEqual(api.calls, [])

    @unittest.skipUnless(platform.system() == "Windows", "Windows listener API")
    def test_actual_owned_disposable_loopback_listener(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            address, port = listener.getsockname()
            self.assertEqual(address, "127.0.0.1")
            self.assertTrue(lab.listening_socket(os.getpid(), port))
            with self.assertRaisesRegex(lab.LabError, "selected PID"):
                lab.listening_socket(os.getpid() + 1, port)
        self.assertEqual(listener.fileno(), -1)
        with self.assertRaisesRegex(lab.LabError, "one 127.0.0.1"):
            lab.listening_socket(os.getpid(), port)


if __name__ == "__main__":
    unittest.main()
