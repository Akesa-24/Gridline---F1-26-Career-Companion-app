"""Default 2026 driver line-up as it ships in the 2026 Season Pack.

Only used for display before telemetry has seen a lobby, and by the simulator.
AI drivers are identified by their game driver id, so if the game's roster
differs the real participant data always wins.
"""
from __future__ import annotations

DEFAULT_GRID: dict[str, list[tuple[int, str, int]]] = {
    # team_key: [(driver_id, name, race_number), ...]
    "mclaren":     [(54, "Lando Norris", 1), (112, "Oscar Piastri", 81)],
    "mercedes":    [(50, "George Russell", 63), (165, "Andrea Kimi Antonelli", 12)],
    "redbull":     [(9, "Max Verstappen", 3), (149, "Isack Hadjar", 6)],
    "ferrari":     [(58, "Charles Leclerc", 16), (7, "Lewis Hamilton", 44)],
    "williams":    [(62, "Alexander Albon", 23), (0, "Carlos Sainz", 55)],
    "rb":          [(113, "Liam Lawson", 30), (188, "Arvid Lindblad", 41)],
    "astonmartin": [(3, "Fernando Alonso", 14), (19, "Lance Stroll", 18)],
    "haas":        [(17, "Esteban Ocon", 31), (147, "Oliver Bearman", 87)],
    "audi":        [(10, "Nico Hulkenberg", 27), (161, "Gabriel Bortoleto", 5)],
    "alpine":      [(59, "Pierre Gasly", 10), (162, "Franco Colapinto", 43)],
    "cadillac":    [(14, "Sergio Perez", 11), (15, "Valtteri Bottas", 77)],
}

DRIVER_NAMES: dict[int, str] = {d[0]: d[1] for seats in DEFAULT_GRID.values() for d in seats}
