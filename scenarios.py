"""
The runs your test needs. ← UNIT 4, MILESTONE 3

Each of your five criteria needs something run against it. A criterion about
the empty-search branch needs an impossible query. One about the fit card needs
the same item run more than once. Working that out is Milestone 3's first step,
and this file is where you write it down.

`run_eval.py` runs everything here five times and writes the run log — five
because your criteria are written out of five.

Three scenarios are filled in to show the shape. Add or change whatever your
own criteria need — these are a starting point, not a fixed set.
"""

SCENARIOS = [
    {
        # A query the data can match. Criterion 1.
        "name": "matching query completes",
        "query": "vintage graphic tee under $30",
        "wardrobe": "example",
        "criterion": 1,
    },
    {
        # A query nothing can match. Criterion 2 — the branch.
        "name": "impossible query stops early",
        "query": "designer ballgown size XXS under $5",
        "wardrobe": "example",
        "criterion": 2,
    },
    {
        # A different, normal query so the selected item isn't always the same
        # one. Compare session["selected_item"] with what suggest_outfit
        # received. Criterion 3 — state matches across tools.
        "name": "selected item reaches suggest_outfit",
        "query": "black leather jacket under $60",
        "wardrobe": "example",
        "criterion": 3,
    },
    {
        # A normal query whose fit card is checked for the item's price, as
        # digits or words. Criterion 4 — fit card includes the price.
        "name": "fit card mentions price",
        "query": "denim jacket under $50",
        "wardrobe": "example",
        "criterion": 4,
    },
    {
        # A populated wardrobe gives the outfit tool something to pair with, so
        # it should return at least two outfits. Criterion 5 — at least 2
        # outfits suggested.
        "name": "outfit tool suggests at least two outfits",
        "query": "vintage graphic tee under $30",
        "wardrobe": "example",
        "criterion": 5,
    },
    #
    # Set "criterion" to the number in criteria.md that the scenario tests.
    # "criterion": None means a diagnostic run — useful to have, but it isn't
    # one of your five, and run_eval.py marks it as such in the table.
    #
    # For a state criterion, any normal query works — what you're checking is
    # what ends up in the session, not what the user typed.
    #
    # For a fit-card criterion, you probably want the SAME query listed more
    # than once, or several different items, depending on what your criterion
    # actually says.
]

WARDROBES = ("example", "empty")


def validate() -> list[str]:
    """Complain about anything malformed, before a long run rather than during."""
    problems = []
    for i, scenario in enumerate(SCENARIOS, 1):
        if not scenario.get("query", "").strip():
            problems.append(f"scenario {i} has no query")
        if scenario.get("wardrobe") not in WARDROBES:
            problems.append(
                f"scenario {i} has wardrobe {scenario.get('wardrobe')!r} — "
                f"it should be one of {WARDROBES}"
            )
    return problems
