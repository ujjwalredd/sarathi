import threading
import unittest

from lease_registry import LeaseRegistry


class FakeClock:
    def __init__(self, value=0):
        self.value = value

    def __call__(self):
        return self.value


class LeaseRegistryTests(unittest.TestCase):
    def test_acquire_and_exact_expiration_boundary(self):
        clock = FakeClock(100)
        leases = LeaseRegistry(clock)
        self.assertTrue(leases.acquire("job", "a", 10))
        self.assertFalse(leases.acquire("job", "b", 50))
        self.assertEqual(leases.holder("job"), "a")
        clock.value = 110
        self.assertIsNone(leases.holder("job"))
        self.assertTrue(leases.acquire("job", "b", 5))
        self.assertEqual(leases.holder("job"), "b")

    def test_renew_and_release_require_active_owner(self):
        clock = FakeClock()
        leases = LeaseRegistry(clock)
        leases.acquire("k", "owner", 4)
        self.assertFalse(leases.renew("k", "stranger", 20))
        self.assertFalse(leases.release("k", "stranger"))
        self.assertTrue(leases.renew("k", "owner", 10))
        clock.value = 9
        self.assertEqual(leases.holder("k"), "owner")
        self.assertTrue(leases.release("k", "owner"))
        self.assertIsNone(leases.holder("k"))

    def test_expired_owner_cannot_renew_or_release(self):
        clock = FakeClock()
        leases = LeaseRegistry(clock)
        leases.acquire("k", "old", 2)
        clock.value = 2
        self.assertFalse(leases.renew("k", "old", 10))
        self.assertFalse(leases.release("k", "old"))
        self.assertTrue(leases.acquire("k", "new", 3))
        self.assertEqual(leases.holder("k"), "new")

    def test_invalid_ttl_does_not_mutate(self):
        clock = FakeClock()
        leases = LeaseRegistry(clock)
        leases.acquire("k", "owner", 20)
        for invalid in (0, -1, 1.5, True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    leases.renew("k", "owner", invalid)
                self.assertEqual(leases.holder("k"), "owner")
        with self.assertRaises(ValueError):
            leases.acquire("missing", "owner", 0)
        self.assertIsNone(leases.holder("missing"))

    def test_same_key_contention_has_one_winner(self):
        for round_number in range(40):
            leases = LeaseRegistry(FakeClock(round_number))
            barrier = threading.Barrier(17)
            results = []

            def contender(index):
                barrier.wait()
                result = leases.acquire("shared", index, 100)
                results.append((index, result))

            threads = [threading.Thread(target=contender, args=(i,)) for i in range(16)]
            for thread in threads:
                thread.start()
            barrier.wait()
            for thread in threads:
                thread.join()
            winners = [owner for owner, won in results if won]
            self.assertEqual(len(results), 16)
            self.assertEqual(len(winners), 1)
            self.assertEqual(leases.holder("shared"), winners[0])


if __name__ == "__main__":
    unittest.main()
