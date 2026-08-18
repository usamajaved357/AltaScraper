"""domain/image_rules.py -- what a GENERATED IMAGE may say and how much
product it may show. ONE copy, used by every path that draws an image.

There were two paths and only one of them had these rules. Secondary images went
through /genimage/from_concept, which checks the words and decides the product
presence; A+ modules went through /aplus/generate, which built its own brief and
had neither. So an A+ module could print a claim that a secondary image would
have been stopped from printing, and every A+ module got the product photograph
attached whether or not the module was a photograph of the product.

That is the same concept handled in two places, which CLAUDE.md Rule 12 forbids.
The rules were MOVED here unchanged (Rule 10: move code, do not rewrite it) and
both paths now import them.

Every rule below was written after seeing the fault in a generated image. The
comments record what was measured, because none of it is visible from the code.
"""


import re


# WHAT AN IMAGE IS ALLOWED TO SAY.
#
# The listing COPY is checked -- IP rules, compliance rules, a ban on medical
# claims and unverifiable superlatives. Text drawn ONTO an image went through
# none of that, and a secondary image is published copy in every way that
# matters to Amazon.
#
# It matters because the MODEL writes the words itself. Asked for a calm
# lifestyle shot with "nothing clinical, nothing medical, no captions", it
# returned a headline reading "Float Into Recovery" -- a health claim, invented,
# on an image that would have gone straight to a live listing. On the Legion
# test it labelled an ingredient panel "AMINO ACIDS / L ranteine", which is not
# an ingredient and is not a word.
#
# THIS LIVED ON ONE PATH ONLY. The hand-built role path had it; the strategist's
# concept path -- the one people actually use, and the one that produced the
# invented ingredient -- did not. One copy, both paths (CLAUDE.md Rule 12).
#
# A LIST IS THE EASIEST PLACE TO LIE.
#
# The first product-free panel generated after the presence fix was an
# ingredient board for a multivitamin, and it was a good design carrying bad
# data. MEASURED on that image:
#
#   * "Magnanese", "Molybdenese", "Setassium", "Mangnesium" -- four misspelt
#     ingredient names, sitting under a headline in perfect type
#   * Copper, Zinc, Iodine, Inositol, Coenzyme Q10 and Alpha Lipoic Acid each
#     printed TWICE, once in each column
#   * a headline reading "28" above a list of considerably more than 28 rows
#
# The listing carried no ingredient list at all, so the model filled the layout
# it had been given. A designed panel has a shape to satisfy, and a model asked
# for two columns WILL produce two full columns whether or not it has the facts.
#
# So the rule is that the SHAPE gives way to the FACTS, never the other way
# round -- and it is general, because the same panel is a spec table for a tool
# and a materials list for a bench.
_LIST_RULES = (
    "\nIF THE IMAGE CONTAINS A LIST, TABLE OR SET OF CALLOUTS:\n"
    "- Every entry must come from the product details above. If there are only "
    "six real entries, show six. NEVER pad a column, a grid or a layout to make "
    "it look full -- a short honest list beats a full invented one, and "
    "inventing a plausible-looking name is the worst outcome of all.\n"
    "- COUNT THE ITEMS FIRST, THEN CHOOSE THE LAYOUT. Four facts get four "
    "slots, not a six-slot grid with two repeated. Never pick a grid shape and "
    "then find things to put in it -- that is how the same label ends up "
    "printed three times, which is what a buyer notices before anything else "
    "on the image.\n"
    "- NO entry may appear twice anywhere in the image. Read back every label "
    "you have drawn and check for repeats before finishing.\n"
    "- If a headline states a COUNT, the number of entries shown must equal it "
    "exactly. If you cannot show that many real entries, change the headline "
    "rather than the list.\n"
    "- Spell every entry exactly as the product details spell it. These are "
    "proper names and a near-miss reads as a counterfeit.\n"
    "- If the details do not contain enough to fill a list at all, do not draw "
    "a list: use the space for one clear statement instead.\n")


# Generic on purpose: it governs every product in every category, so it
# constrains the KIND of statement rather than any particular claim.
_IMAGE_TEXT_RULES = (
    "\n\nRULES FOR ANY TEXT IN THE IMAGE -- these override the brief:\n"
    "- NO health, medical, therapeutic or clinical wording of any kind. Not "
    "'therapy', 'therapeutic', 'treatment', 'recovery', 'healing', 'relief', "
    "'cure', 'symptoms', 'diagnosis', 'wellness benefit', and never the name "
    "of any condition or disorder. Describe what the product IS and what it "
    "physically does.\n"
    "- NO unverifiable superlatives or guarantees: 'best', '#1', 'premium "
    "quality', 'perfect', 'guaranteed', 'lifetime', '100%'.\n"
    # MEASURED on the charcoal set. Three images, three claims, none of them in
    # the listing: "12kg -- that's a full season of weekend grills", "No fillers.
    # No binders.", "Lights fast. Holds heat. Burns clean." Every one reads like
    # a fact and none can be evidenced. The old rules caught invented NUMBERS and
    # invented SUPERLATIVES and let all three of these straight through, because
    # a performance claim is neither.
    "- NO claim about how the product PERFORMS, how LONG it lasts, how much it "
    "does, or what it does NOT contain, unless the product details above state "
    "it. Not 'lights fast', 'holds heat', 'burns clean', 'lasts all season', "
    "'no fillers', 'no additives', 'won't warp'. These read as facts and cannot "
    "be evidenced. Say what the product IS and what the listing actually "
    "states; a plain true line beats an impressive unprovable one.\n"
    # MEASURED: "12 kg -- that's / that's a full / season of weekend grills".
    "- Do not repeat a word across a line break. Read the finished lines as one "
    "sentence and check no word is printed twice where the text wraps.\n"
    # MEASURED: "#B5813A" typeset under the chef-hat mark, straight out of the
    # art direction. Same class as the bullet character: notation describing the
    # design, rendered as though it were copy.
    "- Colour codes, pixel sizes, font names and any other notation from the "
    "art direction are INSTRUCTIONS, never words to print. A hex code like "
    "#B5813A tells you what colour to use; it must never appear in the image.\n"
    "- NO number, measurement, weight, capacity, material or certification "
    "that is not given in the product spec above. If a figure is not stated "
    "there, leave it out entirely rather than estimating a plausible one.\n"
    "- NO ingredient, component or part name that is not given above. An "
    "ingredient panel must list ONLY what the listing states, spelled as the "
    "listing spells it. Inventing a plausible-looking name is worse than "
    "leaving the panel shorter.\n"
    # MEASURED: an "EST. OUTDOORS" oval stamp on an A+ module for a camping mug.
    # The brand was not established by anything called Outdoors and the badge
    # means nothing; it is there because a badge is what that corner of a layout
    # usually holds. The old wording banned awards and seals in the abstract and
    # a decorative stamp did not read as one.
    "- NO invented awards, badges, seals, certifications, ratings or logos. "
    "That includes an EMPTY-LOOKING decorative stamp -- an 'EST.' oval, a "
    "roundel, a ribbon, a crest, a shield. If the listing does not state the "
    "thing the badge asserts, leave the space empty or use it for real words.\n"
    # MEASURED: "2010x50" set as a headline on a 600x450 A+ module. The prompt
    # ends with "output the image at exactly 600x450 pixels", which to a model
    # looks exactly like a line of copy to typeset.
    "- The OUTPUT SIZE is not part of the design. Never print the pixel "
    "dimensions, the aspect ratio, a resolution or any measurement of the image "
    "itself anywhere in the frame. Those numbers tell you what shape to make; "
    "they are not words for the reader.\n"
    "- Every word must be spelled correctly and rendered completely; no "
    "clipped, overlapping or half-drawn characters.\n"
    # MEASURED: the brief writes a bullet as "+ Formulated for athletes", and the
    # model drew a green '+' marker above the line AND kept the '+' at the front
    # of the text. The bullet character in the brief is punctuation describing the
    # list, not a word to be typeset.
    "- A leading bullet character in the brief (+, -, *, or a dot) marks where a "
    "line starts; it is NOT part of the words. Draw the marker OR the character, "
    "never both, and never print the raw character at the front of a line that "
    "already has a drawn bullet.\n"
    + _LIST_RULES)




# ---------------------------------------------------------------------------
# HOW MUCH OF THE PRODUCT AN IMAGE NEEDS
# ---------------------------------------------------------------------------
#
#     "i see the item image in all the seconary images ... There is no need to
#      show the item in all the pictures."
#
# Every secondary image was built the same way: the whole product, on a
# background, with a headline beside it. Eight of those is eight photographs of
# the same bottle, and the slots that could have answered a real doubt were
# spent repeating the main image.
#
# The strongest secondary images on Amazon frequently contain no product at
# all. A wall of journal pages under "3,319 peer-reviewed studies". A
# specification panel with the numbers called out around it. The product is
# already in the main image; these slots are for the things it cannot say.
#
# Four honest answers, and the last one is the one that could not be expressed:
_PRESENCE_RULES = {
    "hero": (
        "THE PRODUCT IS THE SUBJECT. Reproduce it EXACTLY as the reference "
        "photograph shows it -- same shape, proportions, colour, materials and "
        "every line of label text. Do not redesign it to suit the composition; "
        "place the real product in and build around it. Premium, clean, "
        "generous negative space."
    ),
    "detail": (
        "SHOW A PART OF THE PRODUCT, CLOSE UP -- not the whole thing. Fill the "
        "frame with the surface, mechanism, texture or fitting the idea is "
        "about, cropped tight. What IS shown must match the reference exactly "
        "in colour, material and finish. A wide shot of the whole product here "
        "wastes the slot: the main image already does that."
    ),
    "in_use": (
        "THE PRODUCT IS IN A REAL SCENE, not on a backdrop. It may be partly "
        "out of frame, held, or in use -- what matters is that the moment is "
        "believable and belongs to the person who buys this. Where the product "
        "IS visible it must match the reference exactly. Do not fall back to a "
        "studio shot with a lifestyle background pasted behind it."
    ),
    "none": (
        "DO NOT SHOW THE PRODUCT IN THIS IMAGE AT ALL. This slot is a designed "
        "graphic -- a panel, a chart, a comparison, a set of icons, a piece of "
        "evidence -- and putting the product in it would waste the one slot "
        "that can say something the photographs cannot. Build it from "
        "typography, layout and simple iconography in the brand's colours. It "
        "must still look like it belongs beside the other images in the set.\n"
        "IT IS A FLAT GRAPHIC, drawn directly on the canvas. Not a photograph "
        "of a printed panel, not a poster on a wall, not a card lying on a "
        "surface, and above all NOT the design wrapped onto a box or package "
        "-- asked for a graphic, models reach for a packaging mockup, and the "
        "result is a picture of the product after all. No perspective, no 3D, "
        "no drop shadow behind a floating panel, no mock-up.\n"
        "THERE IS NO BOTTLE, BOX, PACK, TUB OR UNIT ANYWHERE IN THE FRAME, at "
        "any size, in the background, blurred, in shadow, or as a silhouette. "
        "If you find yourself placing the product somewhere in the layout, the "
        "layout is wrong -- use the space for the message instead. Take only "
        "the COLOURS and the type style from the brand, never its object."
    ),
}


# An Amazon secondary image is SQUARE, and the model does not assume so.
#
# The first product-free panel came back as a tall poster centred in a square
# frame with white margins down both sides -- a good design occupying about
# half the pixels anyone would ever see. The presence rules say what to draw;
# nothing said what shape to draw it in.
_SQUARE_CANVAS = (
    "\nCANVAS: a 1:1 SQUARE. Compose for a square and FILL IT edge to edge --"
    " the design should reach all four edges, with no letterboxed panel, no"
    " border and no empty margin down the sides. Keep every word and the"
    " important edges of the subject inside the middle 90%, but the BACKGROUND"
    " and layout must run to the edge of the frame."
    # A panel sized for facts it does not have leaves a hole. Having told it to
    # shorten the content rather than invent, it has to be told to re-balance
    # the layout too, or the honesty shows up as half an empty image.
    "\nBALANCE THE WHOLE SQUARE. Whatever content there is should be sized and"
    " spaced to use the full height as well as the full width. If there is less"
    " to say than the layout expected, make the type larger and the spacing"
    " more generous rather than leaving the lower half empty -- a short message"
    " set large is confident, the same message set small above a void looks"
    " unfinished."
)


def _presence_rule(presence):
    """The instruction for how much product this image should contain."""
    return (_PRESENCE_RULES.get(presence or "hero", _PRESENCE_RULES["hero"])
            + _SQUARE_CANVAS)


# ---------------------------------------------------------------------------
# A COLOUR CODE IS NOT A WORD
# ---------------------------------------------------------------------------
#
# "#B5813A" printed under the chef-hat mark on a charcoal panel. "@0D0D00"
# printed in the top-left corner of an A+ module. Both were lifted straight out
# of the art direction, which describes the palette in hex because that is how
# designers write a palette.
#
# Telling the model not to typeset them REDUCED it and did not stop it -- the
# second one happened with the rule already in the prompt. That is the expected
# result: the token is sitting in the text, it looks like a label, and one
# request in some number will draw it.
#
# So the token is REMOVED instead, and replaced with the colour in words. There
# is then nothing to typeset, which is a fix rather than a plea. Naming the
# colour also reads better to the model than six hex digits do.
#
# Deliberately a small, blunt palette: the job is to say "dark olive green" well
# enough that the model picks the right family, not to reproduce the exact
# shade. The exact shade was never going to survive a diffusion model anyway.
_COLOUR_NAMES = (
    ((0, 0, 0), "black"), ((255, 255, 255), "white"),
    ((128, 128, 128), "mid grey"), ((64, 64, 64), "charcoal grey"),
    ((192, 192, 192), "light grey"), ((245, 245, 240), "off-white"),
    ((255, 0, 0), "red"), ((139, 0, 0), "dark red"), ((255, 99, 71), "coral"),
    ((255, 165, 0), "orange"), ((255, 140, 0), "deep orange"),
    ((255, 215, 0), "gold"), ((255, 255, 0), "yellow"),
    ((240, 230, 140), "pale yellow"), ((0, 128, 0), "green"),
    ((34, 139, 34), "forest green"), ((85, 107, 47), "dark olive green"),
    ((144, 238, 144), "light green"), ((64, 224, 208), "turquoise"),
    ((62, 219, 175), "mint green"), ((0, 128, 128), "teal"),
    ((0, 255, 255), "cyan"), ((0, 0, 255), "blue"), ((0, 0, 139), "navy"),
    ((70, 130, 180), "steel blue"), ((135, 206, 235), "sky blue"),
    ((128, 0, 128), "purple"), ((216, 191, 216), "lilac"),
    ((255, 192, 203), "pink"), ((165, 42, 42), "brown"),
    ((210, 180, 140), "tan"), ((245, 222, 179), "cream"),
    ((181, 129, 58), "warm brown"), ((13, 13, 0), "near-black"),
)


def colour_name(hexcode):
    """The nearest plain-English name for a hex colour.

    Nearest by straight RGB distance. Not perceptually correct, and it does not
    need to be -- it only has to land in the right family so the sentence reads
    'dark olive green' instead of '#556B2F'.
    """
    h = str(hexcode or "").strip().lstrip("#@").strip()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return ""
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return ""
    best, bestd = "", None
    for (cr, cg, cb), name in _COLOUR_NAMES:
        d = (cr - r) ** 2 + (cg - g) ** 2 + (cb - b) ** 2
        if bestd is None or d < bestd:
            best, bestd = name, d
    return best


# Matches #RRGGBB, @RRGGBB and #RGB. The leading marker is included so a bare
# six-digit number in the copy (a model number, a year, a quantity) is left
# alone -- removing those would be a worse bug than the one being fixed.
_HEX_RE = re.compile(r"[#@]([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")


def words_for_colours(text):
    """Replace hex colour codes with their names, so none can be typeset.

    Applied to the prompt on its way to the image model, at the one point every
    path goes through. Returns the text unchanged when it contains no codes.
    """
    if not text or ("#" not in text and "@" not in text):
        return text

    def sub(m):
        name = colour_name(m.group(1))
        return ("the colour " + name) if name else m.group(0)

    return _HEX_RE.sub(sub, str(text))
