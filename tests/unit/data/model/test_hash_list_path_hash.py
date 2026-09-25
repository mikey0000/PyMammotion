"""Route ``path_hash`` checks on ``HashList`` — the APK's getDBPathHash() / getHashLineNew() logic."""

from __future__ import annotations

from pymammotion.data.model.hash_list import (
    LINE_HASH_SUB_CMD,
    HashList,
    MowPath,
    MowPathPacket,
    NavGetHashListData,
)

#: A real Luba line list (sub_cmd=3, one frame) and the ``work.path_hash`` it reported.
_LINES = [
    3667983952904009130,
    646511709110769289,
    1732994818604906511,
    7787737794409293617,
    3646198988974926439,
    7866670817324677787,
    2600809897945156892,
    2925952933437268886,
    6962540437114950655,
]
_REPORTED_PATH_HASH = 7372458040660269014


def _line_list_frame(lines: list[int], current_frame: int = 1, total_frame: int = 1) -> NavGetHashListData:
    return NavGetHashListData(
        sub_cmd=LINE_HASH_SUB_CMD, current_frame=current_frame, total_frame=total_frame, data_couple=lines
    )


def _cover_path(lines: list[int], *, transaction_id: int = 1, skip: tuple[int, int] | None = None) -> MowPath:
    """One complete frame holding a two-packet path per line; *skip* drops one (line, path_cur) packet."""
    packets = [
        MowPathPacket(path_hash=line, path_total=2, path_cur=cur)
        for line in lines
        for cur in (1, 2)
        if (line, cur) != skip
    ]
    return MowPath(transaction_id=transaction_id, total_frame=1, current_frame=1, path_packets=packets)


def _map_with_lines(lines: list[int]) -> HashList:
    hash_list = HashList()
    hash_list.update_root_hash_list(_line_list_frame(lines))
    return hash_list


def test_computed_path_hash_matches_the_reported_path_hash() -> None:
    """The report's path_hash is a MurMur hash of the whole ordered line list, not any one line."""
    assert _map_with_lines(_LINES).computed_path_hash == _REPORTED_PATH_HASH


def test_computed_path_hash_depends_on_line_order() -> None:
    assert _map_with_lines(list(reversed(_LINES))).computed_path_hash != _REPORTED_PATH_HASH


def test_computed_path_hash_keeps_zero_placeholders() -> None:
    """The APK hashes zero rows too, so a zero in the list must change the result."""
    assert _map_with_lines([*_LINES, 0]).computed_path_hash != _REPORTED_PATH_HASH


def test_computed_path_hash_is_zero_without_a_line_list() -> None:
    assert HashList().computed_path_hash == 0


def test_mow_path_is_current_when_every_line_is_complete() -> None:
    hash_list = _map_with_lines(_LINES)
    hash_list.update_mow_path(_cover_path(_LINES))

    assert hash_list.is_mow_path_current(_REPORTED_PATH_HASH)


def test_mow_path_is_not_current_with_a_packet_missing() -> None:
    hash_list = _map_with_lines(_LINES)
    hash_list.update_mow_path(_cover_path(_LINES, skip=(_LINES[4], 2)))

    assert not hash_list.is_mow_path_current(_REPORTED_PATH_HASH)
    assert not hash_list.has_mow_path_for_hash(_LINES[4])
    assert hash_list.has_mow_path_for_hash(_LINES[3])


def test_mow_path_is_not_current_for_another_route() -> None:
    hash_list = _map_with_lines(_LINES)
    hash_list.update_mow_path(_cover_path(_LINES))

    assert not hash_list.is_mow_path_current(_REPORTED_PATH_HASH + 1)


def test_path_hash_of_zero_or_one_means_no_route() -> None:
    hash_list = _map_with_lines(_LINES)
    hash_list.update_mow_path(_cover_path(_LINES))

    assert not hash_list.is_mow_path_current(0)
    assert not hash_list.is_mow_path_current(1)


def test_a_line_spanning_frames_needs_both_frames() -> None:
    line = _LINES[0]
    hash_list = _map_with_lines([line])
    first = MowPath(
        transaction_id=1,
        total_frame=2,
        current_frame=1,
        path_packets=[MowPathPacket(path_hash=line, path_total=2, path_cur=1)],
    )
    hash_list.update_mow_path(first)
    assert not hash_list.has_mow_path_for_hash(line)

    second = MowPath(
        transaction_id=1,
        total_frame=2,
        current_frame=2,
        path_packets=[MowPathPacket(path_hash=line, path_total=2, path_cur=2)],
    )
    hash_list.update_mow_path(second)
    assert hash_list.has_mow_path_for_hash(line)


def test_a_new_line_list_replaces_the_old_one_whatever_its_frame_count() -> None:
    hash_list = HashList()
    hash_list.update_root_hash_list(_line_list_frame([111], current_frame=1, total_frame=2))
    hash_list.update_root_hash_list(_line_list_frame([222], current_frame=2, total_frame=2))

    hash_list.update_root_hash_list(_line_list_frame(_LINES))

    assert hash_list.line_root_hashlist == _LINES


def test_prune_incomplete_mow_paths_drops_only_unfinished_transactions() -> None:
    hash_list = HashList()
    hash_list.update_mow_path(_cover_path(_LINES[:1], transaction_id=1))
    hash_list.update_mow_path(
        MowPath(
            transaction_id=2,
            total_frame=3,
            current_frame=1,
            path_packets=[MowPathPacket(path_hash=_LINES[1], path_total=1, path_cur=1)],
        )
    )

    hash_list.prune_incomplete_mow_paths()

    assert list(hash_list.current_mow_path) == [1]
