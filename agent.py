"""
The FitFindr planning loop.

This is the file that makes FitFindr an agent rather than a script. It decides
which tool to run next based on what the last one returned.

If your loop calls all three tools no matter what comes back, you have a list
of function calls. A loop looks at the last result before it picks the next
step. **That branch is the graded part of this unit.**

Build and test your three tools in `tools.py` first. Then come here.

    python agent.py          runs both example paths below
"""

import json
import re
import config
import trace
from mcp_client import call_tool
from tools import search_listings, suggest_outfit, create_fit_card
from generate import generate, ModelUnavailable


# ── session state ─────────────────────────────────────────────────────────────

def new_session(query: str, wardrobe: dict) -> dict:
    """
    A fresh session for one user interaction.

    The session is the single source of truth for a run. Every tool result goes
    in here, and the next tool reads it back out.

    You could pass values straight from one call to the next. It would work,
    and you would not be able to test it — you can't print a variable you have
    already overwritten. Going through the session is what makes the state
    visible, and unit 4 has you write a criterion about exactly that.

    Add fields if you need them.
    """
    return {
        "query": query,              # what the user typed
        "parsed": {},                # description / size / max_price you pulled out of it
        "search_results": [],        # everything search_listings returned
        "selected_item": None,       # the one you chose — goes into suggest_outfit
        "wardrobe": wardrobe,        # the user's wardrobe
        "outfit_suggestion": None,   # what suggest_outfit returned
        "fit_card": None,            # what create_fit_card returned
        "error": None,               # set when the run ended early
    }


# ── query parsing ─────────────────────────────────────────────────────────────

_PARSE_SYSTEM = (
    "You pull search filters out of a shopping request. You reply with one JSON "
    "object and nothing else — no explanation, no code fences."
)

def _parse_query(query: str) -> dict:
    """
    Ask the model for the three filters hiding in a plain-language query.

    The model rather than a regex, because "a tee for under thirty bucks,
    medium" and "size M graphic tee, $30 max" mean the same thing and look
    nothing alike. Temperature 0.0 because the same query has to parse the same
    way on every run — if it doesn't, the agent selects a different item each
    time and the state criterion can never hold.
    """
    prompt = (
        "Pull the search filters out of this shopping request.\n\n"
        f"Request: {query!r}\n\n"
        "Reply with one JSON object, exactly these three keys:\n"
        '  "description" — the garment and style words only, with any price or '
        "size wording removed\n"
        '  "size" — the size asked for, written as it would appear on a label '
        '("M", "W30", "US 9"), or null if none was given\n'
        '  "max_price" — the highest price as a plain number, or null if none '
        "was given\n\n"
        "Examples:\n"
        'Request: "vintage graphic tee under $30, size M"\n'
        '{"description": "vintage graphic tee", "size": "M", "max_price": 30}\n'
        'Request: "something warm for winter"\n'
        '{"description": "warm winter layer", "size": null, "max_price": null}\n'
        'Request: "cheap denim jacket, medium, no more than forty bucks"\n'
        '{"description": "denim jacket", "size": "M", "max_price": 40}\n'
    )
    return _read_filters(generate(prompt, system=_PARSE_SYSTEM, temperature=0.0), query)

def _read_filters(raw: str, query: str) -> dict:
    """
    Turn the model's reply into the three filters, surviving whatever it does
    to the JSON. A parse failure falls back to searching on the whole query —
    a worse search, but still a run rather than a crash.
    """
    filters = {"description": query, "size": None, "max_price": None}

    match = re.search(r"\{.*\}", raw or "", re.S)  # survives ```json fences
    if not match:
        return filters
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return filters
    if not isinstance(data, dict):
        return filters

    filters["description"] = str(data.get("description") or "").strip() or query

    size = data.get("size")
    if isinstance(size, (str, int, float)) and not isinstance(size, bool):
        filters["size"] = str(size).strip() or None

    price = data.get("max_price")
    if isinstance(price, bool):
        price = None  # json true would otherwise cast to 1.0
    if isinstance(price, (int, float)):
        filters["max_price"] = float(price)
    elif isinstance(price, str):
        digits = re.search(r"\d+(?:\.\d+)?", price)
        if digits:
            filters["max_price"] = float(digits.group(0))
    return filters


# ── the stop message ──────────────────────────────────────────────────────────

def _why_nothing_matched(filters: dict) -> str:
    """
    Name the filter that emptied the results, so the message says what to
    change rather than "no results".

    Every search in here is local and free, so diagnosing a miss costs no model
    calls — it just re-runs the search with one filter dropped at a time to see
    which one was responsible.
    """
    description = filters["description"]
    size = filters["size"]
    max_price = filters["max_price"]

    on_words_alone = search_listings(description)
    if not on_words_alone:
        return (
            f"Nothing in the catalogue matches {description!r}. Try plainer "
            f"garment words — 'denim jacket', 'graphic tee', 'cardigan' — or a "
            f"category: tops, bottoms, outerwear, shoes, accessories."
        )

    if size and not search_listings(description, size=size):
        available = sorted({item["size"] for item in on_words_alone})
        return (
            f"{len(on_words_alone)} items match {description!r}, but none in "
            f"size {size}. Sizes in stock for that search: {', '.join(available)}."
        )

    if max_price is not None and not search_listings(description, max_price=max_price):
        cheapest = min(item["price"] for item in on_words_alone)
        return (
            f"{len(on_words_alone)} items match {description!r}, but the "
            f"cheapest is ${cheapest:.2f} — over your ${max_price:.2f} limit. "
            f"Raise the budget to ${cheapest:.2f} and it comes back."
        )

    # Each filter survives on its own, so it's the combination that's empty.
    in_size = search_listings(description, size=size) or on_words_alone
    cheapest = min(item["price"] for item in in_size)
    return (
        f"No {description} in size {size} comes in under ${max_price:.2f}. The "
        f"cheapest one in your size is ${cheapest:.2f} — raise the budget or "
        f"drop the size filter."
    )


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Run the loop once and return the finished session.

    Args:
        query:    what the user asked for, in plain language
                  (e.g. "vintage graphic tee under $30, size M").
        wardrobe: a wardrobe dict — get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py.

    Returns:
        The session dict. **Check session["error"] first** — if it isn't None,
        the run ended early and the later fields will still be None.

    ─────────────────────────────────────────────────────────────────────────
    TODO — build this, following the branch rule you wrote in Milestone 2.

      1. Start a session with new_session().

      2. Count the times round the loop, and call trace.check_iterations(count)
         on each one before you go again. It raises when the count passes
         MAX_ITERATIONS in config.py — see trace.py.

      3. Parse the query into a description, a size, and a max_price. Regex,
         string splitting, or asking the model are all fine — say which you
         chose in your README. Put the result in session["parsed"].

      4. Call search_listings() with what you parsed.
         Put the results in session["search_results"].

         ⚠️ THIS IS THE BRANCH. If nothing came back:
              - put a message in session["error"] saying what the user could
                change — "No results" is not that message
              - return the session
              - do NOT call suggest_outfit with nothing

      5. Choose an item — the first result is fine. Put it in
         session["selected_item"].

      6. Call suggest_outfit() with the selected item and the wardrobe.
         Put the result in session["outfit_suggestion"].

      7. Call create_fit_card() with the outfit and the item.
         Put the result in session["fit_card"].

      8. Return the session.

    ─────────────────────────────────────────────────────────────────────────
    IN UNIT 4 you come back and add two things:

      • Trace calls. One per step. `trace.step("search_listings", inputs=...,
        returned=...)` — see trace.py. Your README needs the output.

      • A handler for ModelUnavailable, so a bad key produces a message rather
        than a stack trace. The import is already at the top of this file.
    """
    session = new_session(query, wardrobe)

    # The loop runs on a stage rather than a fixed sequence of calls: each turn
    # finishes one step and names the next, and the branch below picks a
    # different next stage depending on what came back.
    stage = "parse"
    iterations = 0

    while stage != "done":
        iterations += 1
        trace.check_iterations(iterations)

        if stage == "parse":
            session["parsed"] = _parse_query(session["query"])
            stage = "search"

        elif stage == "search":
            filters = session["parsed"]
            session["search_results"] = call_tool("search_listings", {
                "description": filters["description"],
                "size": filters["size"],
                "max_price": filters["max_price"],
            })

            # ── THE BRANCH ───────────────────────────────────────────────────
            # Empty list → say what to change and stop. suggest_outfit never
            # gets called with nothing.
            if not session["search_results"]:
                session["error"] = _why_nothing_matched(filters)
                stage = "done"
            else:
                session["selected_item"] = session["search_results"][0]
                stage = "suggest"

        elif stage == "suggest":
            session["outfit_suggestion"] = suggest_outfit(
                session["selected_item"], session["wardrobe"]
            )
            stage = "card"

        elif stage == "card":
            session["fit_card"] = create_fit_card(
                session["outfit_suggestion"], session["selected_item"]
            )
            stage = "done"

    return session


# ── running it directly ───────────────────────────────────────────────────────

def _show(session: dict) -> None:
    if session["error"]:
        print(f"  stopped: {session['error']}")
        print(f"  fit_card is {session['fit_card']!r} — it should still be None here")
        return

    item = session["selected_item"] or {}
    print(f"  found:    {item.get('title')} — ${item.get('price')} on {item.get('platform')}")
    print(f"  outfit:   {session['outfit_suggestion']}")
    print(f"  fit card: {session['fit_card']}")


if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe

    print("=== A query the data can match ===")
    _show(run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    ))

    print("\n=== A query it can't ===")
    _show(run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    ))

    print(
        "\nThe second one should stop before the fit card. If both paths look "
        "the same,\nthe branch isn't doing anything yet."
    )
