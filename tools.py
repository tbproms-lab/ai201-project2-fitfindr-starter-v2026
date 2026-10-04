"""
The three FitFindr tools.

Each one is a standalone function you can call and test on its own, before any
of them are wired into the loop. Build and test them one at a time — three
untested tools joined by a loop is one problem that looks like six, because you
can't tell which layer is lying to you.

    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)             → str
    create_fit_card(outfit, new_item)              → str

All three are stubs right now. They run and they do nothing — that's the
starting position and it's deliberate.

⚠️ Before you write any of them, fill in the **Tool Inventory** section of your
README (Milestone 2). Four lines per tool: what it does, each input with its
type, exactly what it returns, and what it returns when it has nothing to give.
That last line is what your loop branches on. "Returns a list" earns nothing —
the description has to say what is *in* the list.
"""

import re
import config
from generate import generate
from utils.data_loader import load_listings


# ── Tool 1: search_listings ───────────────────────────────────────────────────

_STOPWORDS = {"a", "an", "the", "and", "or", "but", "in","on", "at",
               "to", "for", "with", "above", "below", "from", "by",
               "as", "is", "was", "are", "were", "been", "being",
               "looking", "look", "want", "need", "find", "show", "me", "my",
               "something", "really", "very", "just", "great", "perfect",
               "nice", "good", "some", "no", "any", "like", "of", "it", "its",
               "this", "that", "be", "can", "under", "over", "size"}

def _keywords(text: str) -> set[str]:
    """Lowercase words worth matching on, stopwords removed."""
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    return {w for w in words if w not in  _STOPWORDS and len(w) > 1}

def _size_tokens(size: str) -> set[str]:
    cleaned = re.sub(r"\([^)]*\)", " ", size or "") # drop parenthesized parts
    tokens = set()
    for part in cleaned.split("/"):
        part = " ".join(part.split()).upper()  # collapse runs of whitespace
        if not part:
            continue
        tokens.add(part)
        # "W30 L30" should answer to "W30". Only waist/length pieces get split
        # on whitespace — splitting every size would put "US" in both "US 8"
        # and "US 9", and then every shoe matches every other shoe.
        if re.fullmatch(r"[WL]\d+(?: [WL]\d+)+", part):
            tokens.update(part.split())
        # "US 9" should also answer to a plain "9" or a spaceless "US9".
        shoe = re.fullmatch(r"US ?(\d+(?:\.\d+)?)", part)
        if shoe:
            tokens.add(shoe.group(1))
            tokens.add("US" + shoe.group(1))
    return tokens

def _size_matches(wanted: str, listing_size: str) -> bool:
    if not wanted:
        return True
    listing_tokens = _size_tokens(listing_size)
    if any(token.startswith("ONE SIZE") for token in listing_tokens):
        return True
    return bool(_size_tokens(wanted) & listing_tokens)

# What a keyword match is worth, depending on where it lands. The same word
# says more from a title or a style tag than it does buried in the prose.
_FIELD_WEIGHTS = {
    "title": 3,
    "style_tags": 3,
    "category": 2,
    "colors": 2,
    "brand": 2,
    "description": 1,
}

def _field_text(listing: dict, field: str) -> str:
    """One searchable string for a field, whether it holds a list, a str, or None."""
    value = listing.get(field)
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value or "")  # brand is None on most listings

def _word_matches(keyword: str, word: str) -> bool:
    """Whole-word match, forgiving a trailing plural s on either side."""
    return keyword == word or keyword == word + "s" or word == keyword + "s"

def _score(keywords: set[str], listing: dict) -> int:
    """How well one listing answers the keywords. Zero means no overlap at all."""
    total = 0
    for field, weight in _FIELD_WEIGHTS.items():
        words = _keywords(_field_text(listing, field))
        for keyword in keywords:
            if any(_word_matches(keyword, word) for word in words):
                total += weight
    return total

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the listings data for items matching a description, and optionally a
    size and a price ceiling.

    This is the tool that doesn't call the model, which makes it the easiest one
    to test and the one to move onto MCP in unit 4.

    Args:
        description: keywords describing what the user wants
                     (e.g. "vintage graphic tee").
        size:        a size string to filter by, or None to skip size filtering.
                     Match case-insensitively — "M" should match "S/M".

                     ⚠️ Read the sizes in the data before you reach for a plain
                     substring test. `"s" in "us 9"` is True, and so is
                     `"l" in "xl"`. A filter that returns shoes when someone
                     asked for a small top reads like a broken search, and it
                     will quietly cost you in unit 4 when you test criterion 1.
                     What counts as a size match is part of your spec — decide
                     it and write it into your Tool Inventory.
        max_price:   maximum price, inclusive, or None to skip price filtering.

    Returns:
        A list of matching listing dicts, best match first.
        **Returns an empty list when nothing matches — an empty list, not None,
        and not an exception.** Your loop branches on this.

    Each listing dict has these fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand (str or None), platform

    Note that `brand` is None for most listings. That is deliberate and
    realistic — thrift listings often have no brand. If something you write
    assumes a brand is always there, you will find out in unit 4.

    TODO:
        1. Load every listing with load_listings().
        2. Filter by max_price and by size, when each is provided.
        3. Score what's left by keyword overlap with `description`.
        4. Drop anything scoring zero.
        5. Sort by score, highest first, and return the listing dicts —
           at most config.SEARCH_RESULT_LIMIT of them.

    Test it from a terminal before you move on:
        python -c "from tools import search_listings; print(search_listings('graphic tee', max_price=30))"
    """
    keywords = _keywords(description)
    if not keywords:
        return []

    scored = []
    for listing in load_listings():
        if max_price is not None and listing["price"] > max_price:
            continue
        if not _size_matches(size, listing["size"]):
            continue
        score = _score(keywords, listing)
        if score > 0:
            scored.append((score, listing))

    # Best match first; a cheaper item wins a tie, which also keeps the order
    # stable so the agent picks the same item on every run.
    scored.sort(key=lambda pair: (-pair[0], pair[1]["price"]))
    return [listing for _, listing in scored[:config.SEARCH_RESULT_LIMIT]]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

_OUTFIT_SYSTEM = (
    "You are a thrift stylist helping someone decide whether a second-hand find "
    "will work with what they already own. Be concrete about colour, silhouette "
    "and when they'd wear it. Never invent clothing you haven't been told about. "
    "No preamble, no markdown headings, under 150 words."
)

def _item_summary(item: dict) -> str:
    """The listing, written out for the model. Skips fields the data doesn't have."""
    lines = [f"Title: {item.get('title') or 'unknown item'}"]
    if item.get("brand"):  # None on most listings — better silent than "Brand: None"
        lines.append(f"Brand: {item['brand']}")
    lines.append(f"Category: {item.get('category') or 'not stated'}")
    lines.append(f"Colors: {', '.join(item.get('colors') or []) or 'not stated'}")
    lines.append(f"Style tags: {', '.join(item.get('style_tags') or []) or 'not stated'}")
    lines.append(f"Size: {item.get('size') or 'not stated'}")
    lines.append(f"Condition: {item.get('condition') or 'not stated'}")

    price = item.get("price")
    platform = item.get("platform") or "an unnamed platform"
    if isinstance(price, (int, float)):
        lines.append(f"Price: ${price:.2f} on {platform}")
    else:
        lines.append(f"Listed on {platform}")

    if item.get("description"):
        lines.append(f"Seller's description: {item['description']}")
    return "\n".join(lines)

def _wardrobe_lines(items: list[dict]) -> str:
    """One bullet per owned piece, so the model can name them back exactly."""
    lines = []
    for item in items:
        details = [d for d in (
            item.get("category"),
            ", ".join(item.get("colors") or []),
            ", ".join(item.get("style_tags") or []),
        ) if d]
        line = f"- {item.get('name') or 'unnamed item'}"
        if details:
            line += f" ({'; '.join(details)})"
        if item.get("notes"):  # optional in the schema, and null on several items
            line += f" — {item['notes']}"
        lines.append(line)
    return "\n".join(lines)

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest one or two outfits.

    This one calls the model, through `generate()`. You don't need to think
    about rate limits — the adapter handles pacing for you.

    Args:
        new_item: a listing dict — the item the user is considering.
        wardrobe: a wardrobe dict with an 'items' key holding a list of items.
                  **It may be empty.** Handle that.

    Returns:
        A non-empty string with outfit suggestions.
        With an empty wardrobe, return general styling advice rather than
        raising or returning "". Unit 4 has you trigger the empty wardrobe on
        purpose, so decide now what it should do.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If it is, ask the model for general styling ideas for this item.
        3. If it isn't, format the wardrobe items into the prompt and ask for
           specific combinations naming pieces the user already owns.
        4. Return the model's response.

    Test it from a terminal before you move on:
        python -c "from tools import suggest_outfit; from utils.data_loader import get_example_wardrobe, load_listings; print(suggest_outfit(load_listings()[0], get_example_wardrobe()))"
    """
    # A missing 'items' key and an empty list are the same situation to us.
    items = (wardrobe or {}).get("items") or []
    item_text = _item_summary(new_item or {})

    if not items:
        prompt = (
            "Someone is considering this second-hand item:\n\n"
            f"{item_text}\n\n"
            "Their wardrobe is empty, so you don't know a single thing they own "
            "and must not guess. Suggest two ways to style this piece around "
            "common staples, naming the staples plainly — \"straight-leg blue "
            "jeans\", \"plain white tee\" — so they can check what they have. "
            "Finish with one line on what to pair with it next."
        )
    else:
        prompt = (
            "Someone is considering this second-hand item:\n\n"
            f"{item_text}\n\n"
            f"Here is their whole wardrobe, {len(items)} pieces:\n\n"
            f"{_wardrobe_lines(items)}\n\n"
            "Suggest one or two outfits combining the item with pieces from that "
            "list. Use only pieces from the list, and name each one exactly as it "
            "is written there so they can tell which is which. Give each outfit "
            "one line on why it works."
        )

    suggestion = generate(prompt, system=_OUTFIT_SYSTEM).strip()
    if not suggestion:
        # The contract is a non-empty string, so a silent model doesn't get to
        # hand the loop an empty one — create_fit_card branches on this.
        return (
            f"No styling ideas came back for the "
            f"{new_item.get('title', 'item') if new_item else 'item'}. "
            f"Try again, or pick another item from the search results."
        )
    return suggestion


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

_FIT_CARD_SYSTEM = (
    "You write the caption that goes with a thrift find — the kind a person "
    "posts, not the kind a shop writes. First person, present tense, plain "
    "sentences. Two to four sentences and nothing else: no headings, no bullet "
    "points, no preamble, no quotation marks around the caption."
)

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Write a short caption someone would actually post about the find.

    This calls the model too.

    Args:
        outfit:   the outfit suggestion string from suggest_outfit().
        new_item: the listing dict for the item.

    Returns:
        A two-to-four sentence caption.
        If `outfit` is empty or whitespace, return a descriptive message rather
        than raising.

    The caption should read like a real post rather than a product description,
    mention the item and its price and platform once each, and be specific about
    the vibe.

    It should also come out **differently for different inputs**. If you run
    this three times on the same item and get three word-for-word identical
    strings, it's one of two things, and both are near the top of `config.py`:

        • CACHE_ENABLED — the adapter handed back an answer it already had
        • TEMPERATURE   — at 0.0 the model gives the same words every time

    TODO:
        1. Guard against an empty or whitespace-only `outfit`.
        2. Build a prompt with the item details and the outfit.
        3. Call generate() and return the response.

    Test it from a terminal before you move on:
        python -c "from tools import create_fit_card; from utils.data_loader import load_listings; print(create_fit_card('jeans and white sneakers', load_listings()[0]))"
    """
    item = new_item or {}
    title = item.get("title") or "this item"

    # suggest_outfit promises a non-empty string, but this tool is called on
    # its own too, and there's nothing to caption without an outfit.
    if not (outfit or "").strip():
        return (
            f"No fit card for the {title} — there's no outfit to caption. "
            f"Run suggest_outfit first and pass what it returns."
        )

    price = item.get("price")
    price_text = f"${price:.2f}" if isinstance(price, (int, float)) else "the listed price"
    platform = item.get("platform") or "the app"

    prompt = (
        "Someone just found this second-hand and is posting about it:\n\n"
        f"{_item_summary(item)}\n\n"
        "Here is how they plan to wear it:\n\n"
        f"{outfit.strip()}\n\n"
        f"Write their caption. Work in the piece itself, the {price_text} it "
        f"cost, and that it came from {platform} — each exactly once, woven "
        "into the sentences rather than listed. Be specific about the vibe and "
        "where they'd wear it; name something concrete from the outfit above "
        "instead of calling it 'a great look'."
    )

    caption = generate(prompt, system=_FIT_CARD_SYSTEM).strip()
    if not caption:
        return (
            f"No caption came back for the {title}. Try again — the outfit "
            f"suggestion itself is fine."
        )
    return caption
