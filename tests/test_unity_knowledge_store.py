import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from memory.unity_knowledge import UnityKnowledgeStore


class UnityKnowledgeStoreTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(
            self.temporary_directory.name,
            "memory",
            "unity_knowledge.json",
        )
        self.current_time = datetime(2026, 8, 15, 4, 0, tzinfo=timezone.utc)
        self.store = UnityKnowledgeStore(self.path, now=lambda: self.current_time)
        self.evidence = [
            {
                "schema_version": 1,
                "title": "Object.Destroy",
                "url": "https://docs.unity3d.com/2022.3/Documentation/ScriptReference/Object.Destroy.html",
                "excerpt": "Removes an object after the current Update loop.",
            }
        ]

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_missing_cache_returns_an_empty_list(self):
        self.assertEqual(
            [],
            self.store.get("Object.Destroy", "2022.3.62f2c1", {}),
        )

    def test_cache_key_is_stable_across_whitespace_and_package_order(self):
        first = UnityKnowledgeStore.cache_key(
            "  Object.Destroy   usage ",
            "2022.3.62f2c1",
            {"com.unity.inputsystem": "1.7.0", "com.unity.test-framework": "1.1.33"},
        )
        second = UnityKnowledgeStore.cache_key(
            "object.destroy usage",
            "2022.3.62f2c1",
            {"com.unity.test-framework": "1.1.33", "com.unity.inputsystem": "1.7.0"},
        )

        self.assertEqual(first, second)

    def test_put_is_atomic_and_reloads_the_versioned_entry(self):
        key = self.store.put(
            "Object.Destroy usage",
            "2022.3.62f2c1",
            {"com.unity.test-framework": "1.1.33"},
            self.evidence,
            ttl_seconds=3600,
        )

        reloaded = UnityKnowledgeStore(self.path, now=lambda: self.current_time)

        self.assertEqual(64, len(key))
        self.assertEqual(
            self.evidence,
            reloaded.get(
                "Object.Destroy usage",
                "2022.3.62f2c1",
                {"com.unity.test-framework": "1.1.33"},
            ),
        )
        self.assertFalse(os.path.exists(self.path + ".tmp"))
        with open(self.path, "r", encoding="utf-8") as cache_file:
            self.assertEqual(1, json.load(cache_file)["schema_version"])

    def test_expired_entry_is_a_cache_miss(self):
        self.store.put(
            "Object.Destroy",
            "2022.3.62f2c1",
            {},
            self.evidence,
            ttl_seconds=60,
        )
        self.current_time += timedelta(seconds=61)

        self.assertEqual(
            [],
            self.store.get("Object.Destroy", "2022.3.62f2c1", {}),
        )

    def test_get_returns_a_defensive_copy(self):
        self.store.put(
            "Object.Destroy",
            "2022.3.62f2c1",
            {},
            self.evidence,
        )

        loaded = self.store.get("Object.Destroy", "2022.3.62f2c1", {})
        loaded[0]["title"] = "changed"

        self.assertEqual(
            "Object.Destroy",
            self.store.get("Object.Destroy", "2022.3.62f2c1", {})[0]["title"],
        )

    def test_rejects_malformed_or_unsupported_cache_files(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        for content in ("not-json", '{"schema_version": 2, "entries": {}}'):
            with self.subTest(content=content):
                with open(self.path, "w", encoding="utf-8") as cache_file:
                    cache_file.write(content)
                with self.assertRaisesRegex(ValueError, "Unity knowledge cache"):
                    UnityKnowledgeStore(self.path)

    def test_rejects_invalid_put_arguments(self):
        with self.assertRaisesRegex(ValueError, "evidence"):
            self.store.put("query", "2022.3", {}, {}, ttl_seconds=60)
        with self.assertRaisesRegex(ValueError, "ttl_seconds"):
            self.store.put("query", "2022.3", {}, [], ttl_seconds=0)


if __name__ == "__main__":
    unittest.main()
