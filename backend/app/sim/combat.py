"""Dice and attack-sequence math based on the AoS4 core rules.

The attack sequence per the core rules: for each attack roll to Hit,
then to Wound, then the defender makes a Save roll modified by Rend;
unsaved attacks inflict Damage. Stats parsed from Wahapedia are display
strings ("3+", "D6", "2D6+1", "-") and are resolved here, either by
actual dice rolls (Monte Carlo, used by the simulator) or as expected
values (used by the AI to pick targets).
"""

from __future__ import annotations

import random
import re


def roll_value(stat: str, rng: random.Random) -> int:
    """Resolve a stat like '2', 'D6', '2D3+1' to a rolled value."""
    s = (stat or "").strip().upper().replace(" ", "")
    if not s or s in {"-", "—"}:
        return 0
    m = re.fullmatch(r"(?:(\d*)D(\d+))?([+-]\d+)?(\d+)?", s)
    if not m:
        return 0
    count, die, mod, flat = m.groups()
    total = 0
    if die:
        n = int(count) if count else 1
        total += sum(rng.randint(1, int(die)) for _ in range(n))
    if flat and not die:
        total += int(flat)
    if mod:
        total += int(mod)
    return max(total, 0)


def expected_value(stat: str) -> float:
    """Expected value of a stat expression, for AI heuristics."""
    s = (stat or "").strip().upper().replace(" ", "")
    if not s or s in {"-", "—"}:
        return 0.0
    m = re.fullmatch(r"(?:(\d*)D(\d+))?([+-]\d+)?(\d+)?", s)
    if not m:
        return 0.0
    count, die, mod, flat = m.groups()
    total = 0.0
    if die:
        n = int(count) if count else 1
        total += n * (int(die) + 1) / 2
    if flat and not die:
        total += int(flat)
    if mod:
        total += int(mod)
    return max(total, 0.0)


def target_number(stat: str) -> int | None:
    """'3+' -> 3. Returns None for '-' (auto-fail / no roll)."""
    m = re.match(r"(\d)\+", (stat or "").strip())
    return int(m.group(1)) if m else None


def rend_value(stat: str) -> int:
    m = re.search(r"\d+", stat or "")
    return int(m.group()) if m else 0


def _roll_passes(rng: random.Random, base_target: int, delta: int) -> bool:
    """One D6 roll against a modified target number. Unmodified 1 always
    fails and 6 always succeeds (core rules)."""
    roll = rng.randint(1, 6)
    if roll == 1:
        return False
    if roll == 6:
        return True
    return roll >= base_target + delta


def roll_attacks(
    weapon: dict, models: int, rng: random.Random, mods: dict | None = None
) -> int:
    """Wounding hits from one unit's attacks with one weapon profile.
    ``mods`` carries structured-ability deltas ('hit'/'wound', already
    capped at +/-1; negative improves the roll)."""
    mods = mods or {}
    hit_t = target_number(weapon["hit"])
    wound_t = target_number(weapon["wound"])
    if hit_t is None or wound_t is None:
        return 0
    total = 0
    attacks = sum(roll_value(weapon["attacks"], rng) for _ in range(models))
    crit_two_hits = any("2 Hits" in a for a in weapon.get("abilities", []))
    for _ in range(attacks):
        roll = rng.randint(1, 6)
        if roll == 1 or (roll != 6 and roll < hit_t + mods.get("hit", 0)):
            continue
        hits = 2 if (roll == 6 and crit_two_hits) else 1
        for _ in range(hits):
            if _roll_passes(rng, wound_t, mods.get("wound", 0)):
                total += 1
    return total  # number of wounding hits; saves applied by caller


def resolve_damage(
    wounding_hits: int,
    weapon: dict,
    save_stat: str,
    rng: random.Random,
    atk_mods: dict | None = None,
    def_mods: dict | None = None,
) -> int:
    """Apply save rolls (modified by Rend) and roll damage.

    Returns the damage added to the damage pool — Ward saves are NOT
    rolled here. Per the AoS4 damage sequence the whole attack's damage
    accumulates into a pool first, then the target rolls a Ward die per
    damage point (see ``unit_attack`` / ``ward_roll``).

    ``atk_mods`` may add 'rend'/'damage'; ``def_mods`` may shift 'save'
    (negative improves the save, same convention as roll targets)."""
    atk_mods = atk_mods or {}
    def_mods = def_mods or {}
    save_t = target_number(save_stat)
    rend = max(0, rend_value(weapon["rend"]) + atk_mods.get("rend", 0))
    dmg_bonus = atk_mods.get("damage", 0)
    pool = 0
    for _ in range(wounding_hits):
        if save_t is not None:
            needed = save_t + rend + def_mods.get("save", 0)
            if needed <= 6 and rng.randint(1, 6) >= needed:
                continue  # saved
        pool += max(1, (roll_value(weapon["damage"], rng) or 1) + dmg_bonus)
    return pool


def ward_roll(damage: int, ward_stat: str, rng: random.Random) -> tuple[int, int]:
    """Roll a Ward save against ``damage`` points (used for mortal
    wounds, which skip normal saves but not wards).
    Returns ``(damage_through, warded)``."""
    ward_t = target_number(ward_stat)
    if ward_t is None:
        return damage, 0
    through = 0
    for _ in range(damage):
        if rng.randint(1, 6) < ward_t:
            through += 1
    return through, damage - through


def unit_attack(
    attacker_weapons: list[dict],
    models: int,
    defender_save: str,
    rng: random.Random,
    defender_ward: str = "",
    atk_mods: dict | None = None,
    def_mods: dict | None = None,
) -> tuple[int, int]:
    """Full attack sequence for all of a unit's weapon profiles.

    AoS4 damage sequence: every profile's post-save damage accumulates
    into one damage pool, and only then does the defender roll a Ward
    die for each point in the pool. Returns ``(damage, warded)``."""
    pool = 0
    for weapon in attacker_weapons:
        wounds = roll_attacks(weapon, models, rng, atk_mods)
        pool += resolve_damage(
            wounds, weapon, defender_save, rng, atk_mods, def_mods
        )
    return ward_roll(pool, defender_ward, rng)


def expected_damage(weapons: list[dict], models: int, defender_save: str) -> float:
    """Expected damage output, used by the AI to rank targets."""
    save_t = target_number(defender_save)
    total = 0.0
    for w in weapons:
        hit_t = target_number(w["hit"])
        wound_t = target_number(w["wound"])
        if hit_t is None or wound_t is None:
            continue
        p_hit = (7 - hit_t) / 6
        p_wound = (7 - wound_t) / 6
        rend = rend_value(w["rend"])
        if save_t is None or save_t + rend > 6:
            p_unsaved = 1.0
        else:
            p_unsaved = (save_t + rend - 1) / 6
        dmg = expected_value(w["damage"]) or 1.0
        total += expected_value(w["attacks"]) * models * p_hit * p_wound * p_unsaved * dmg
    return total
