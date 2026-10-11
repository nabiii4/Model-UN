"""The fear meter (BUILD_PROMPT.md section 8.4): 100 = scary, 0 = befriended."""


def fear_after_round(value, *, final_heat, base_difficulty, mode="type", avg_listening=None):
    drop = 10
    if final_heat >= base_difficulty:
        drop += 5
    if mode == "speak":
        drop += 5
    if avg_listening is not None and avg_listening >= 2:
        drop += 5
    new_value = max(0, int(value) - drop)
    return new_value, drop
