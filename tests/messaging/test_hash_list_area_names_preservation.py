"""Regression tests for HashList area-name preservation.

These cover SITE A of the area_name wipe issue: the silent racy filter inside
``HashList.update_hash_lists`` that previously dropped names whose hash was no
longer in the current ``self.area`` dict OR the new hashlist.  That dropped
names mid-fetch, before the area frame for the hash had arrived.

The fixed behaviour:
  * ``area_name`` entries are NEVER dropped by ``update_hash_lists``.
  * New hashes get a placeholder name added (existing legacy behaviour in
    ``HashList.update`` when an AREA frame arrives, which calls
    ``update_hash_lists`` after assigning).
  * In-place rename of an existing entry preserves object identity (no list
    churn for downstream consumers).
"""

from __future__ import annotations

from pymammotion.data.model.hash_list import AreaHashNameList, HashList


class TestUpdateHashListsPreservesAreaNames:
    def test_update_hash_lists_preserves_existing_names(self) -> None:
        """Existing names must survive when their hash is not in the new hashlist.

        Pre-fix this would silently drop hash 200 because it wasn't in the new
        hashlist nor the (empty) ``self.area`` dict — wiping a valid
        previously-resolved name mid-fetch.
        """
        hl = HashList()
        hl.area_name = [
            AreaHashNameList(name="Front", hash=100),
            AreaHashNameList(name="Back", hash=200),
        ]

        # New hashlist contains only hash 100 — but 200's name was already
        # resolved on a prior cycle and must survive.
        hl.update_hash_lists([100])

        names_by_hash = {a.hash: a.name for a in hl.area_name}
        assert names_by_hash == {100: "Front", 200: "Back"}

    def test_update_hash_lists_appends_new_hash_without_dropping_others(self) -> None:
        """New hashes in the hashlist must not displace existing names."""
        hl = HashList()
        hl.area_name = [AreaHashNameList(name="Front", hash=100)]

        hl.update_hash_lists([100, 300])

        names_by_hash = {a.hash: a.name for a in hl.area_name}
        # "Front" must be preserved; entry for 300 may or may not be added by
        # this method (it is added by HashList.update on AREA-frame arrival).
        assert names_by_hash[100] == "Front"

    def test_update_hash_lists_with_empty_hashlist_is_noop(self) -> None:
        """An empty hashlist must not wipe area_name (early return)."""
        hl = HashList()
        hl.area_name = [AreaHashNameList(name="Front", hash=100)]

        hl.update_hash_lists([])

        assert len(hl.area_name) == 1
        assert hl.area_name[0].name == "Front"

    def test_update_hash_lists_does_not_duplicate_existing_entries(self) -> None:
        """Repeated calls with the same hashes must not create duplicates."""
        hl = HashList()
        hl.area_name = [AreaHashNameList(name="Front", hash=100)]

        hl.update_hash_lists([100])
        hl.update_hash_lists([100])

        assert len(hl.area_name) == 1
        assert hl.area_name[0].hash == 100


