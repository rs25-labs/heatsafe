from heatsafe.routing import candidate_paths, path_length
from heatsafe.shade import fractions_from_mask
from tests.synthetic import COLS, build_store, node_id, node_latlng, sample_in_sun


def paths_for_grid():
    store = build_store()
    fractions = fractions_from_mask(store, sample_in_sun(store))
    paths = candidate_paths(store.graph, node_latlng(0, 0), node_latlng(0, COLS - 1), fractions)
    return store, paths


def test_fastest_first() -> None:
    store, paths = paths_for_grid()
    assert path_length(store.graph, paths[0]) == 500
    assert [u for u, _, _ in paths[0]] == [node_id(0, c) for c in range(COLS - 1)]


def test_shadiest_differs_from_fastest() -> None:
    _, paths = paths_for_grid()
    assert len(paths) >= 2
    shady_nodes = {u for u, _, _ in paths[1]}
    assert node_id(1, 2) in shady_nodes


def test_no_near_duplicate_paths() -> None:
    _, paths = paths_for_grid()
    edge_sets = [{frozenset((u, v)) for u, v, _ in path} for path in paths]
    for i in range(len(edge_sets)):
        for j in range(i + 1, len(edge_sets)):
            shared = len(edge_sets[i] & edge_sets[j]) / min(len(edge_sets[i]), len(edge_sets[j]))
            assert shared < 0.8


def test_detour_cap_1_6x() -> None:
    store, paths = paths_for_grid()
    fastest = path_length(store.graph, paths[0])
    assert all(path_length(store.graph, path) <= 1.6 * fastest for path in paths)


def test_unreachable_destination_returns_no_paths() -> None:
    store = build_store()
    store.graph.add_node(999, x=417_000.0 + 2_000, y=3_735_000.0 + 2_000)
    fractions = fractions_from_mask(store, sample_in_sun(store))
    from tests.synthetic import latlng_at

    assert candidate_paths(store.graph, node_latlng(0, 0), latlng_at(419_000.0, 3_737_000.0), fractions) == []
