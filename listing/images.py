"""listing/images.py -- which image slots a listing has, and what may go in them.

WHERE THE SLOTS COME FROM
The product type's own schema, never a list written here. SPACE_HEATER on the
live UK account defines EIGHTEEN image attributes (read 14 Aug 2026):

    main_product_image_locator            the one customers see first
    other_product_image_locator_1..8      the gallery, PT1 to PT8
    swatch_product_image_locator          the variation picker thumbnail
    main_offer_image_locator              offer images, a separate set
    other_offer_image_locator_1..5
    image_locator_eeuk                    UK Energy Efficiency Label
    image_locator_pfuk                    UK Product Fiche Label

The last two exist because it is a heater sold in the UK. Another product type
has a different set, and hardcoding nine slots would offer people boxes that do
not exist on their listing and hide the ones that do -- so the list is read from
the schema every time.

WHAT AMAZON WILL ACCEPT IN ONE
The schema says so literally: media_location is required, and its pattern is
^(https?|s3)://. So an app-internal /media/... path is not a URL Amazon can use
-- it has to fetch the image over the open internet, and a path only this app can
resolve fails at the far end with nothing useful said about why. That is checked
here rather than discovered afterwards.

THE SLOT IS NOT A DETAIL
Amazon judges the MAIN image far more strictly than the rest: pure white
background, no text, no logos, no props. A lifestyle shot that is perfectly good
as PT3 gets the listing suppressed as MAIN. Nothing here can measure an image,
but it can make sure nobody sends one to the wrong slot without being told which
slot they are sending it to and what that slot is for.
"""
import re

MAIN = "main_product_image_locator"
SWATCH = "swatch_product_image_locator"

# Amazon's own pattern for media_location, from the schema.
URL_OK = re.compile(r"^(https?|s3)://", re.I)

# What each family of slot is for, in words. Kept short because it is shown next
# to the choice, at the moment the choice is made.
_MEANING = {
    MAIN: ("Main image", "The first image customers see. Amazon's strictest "
                         "rules apply: pure white background, no text, no logos, "
                         "no props — a lifestyle shot here gets the listing "
                         "suppressed."),
    SWATCH: ("Swatch", "The little colour/pattern thumbnail in the variation "
                       "picker. Only meaningful on a listing that is part of a "
                       "variation family."),
}
_OTHER_RE = re.compile(r"^other_product_image_locator_(\d+)$")
_OFFER_RE = re.compile(r"^(main|other)_offer_image_locator(?:_(\d+))?$")


def slots_from_schema(schema):
    """Every image slot this product type defines, in the order to show them.

    Returns [{key, label, group, help}]. Empty when the schema could not be read
    -- which the caller must report as "could not check", not as "no slots".
    """
    props = ((schema or {}).get("properties") or {})
    out = []
    for key in props:
        if "image" not in key.lower():
            continue
        node = props.get(key) or {}
        title = str(node.get("title") or "").strip()

        if key == MAIN:
            label, help_ = _MEANING[MAIN]
            out.append({"key": key, "label": label, "group": "product",
                        "order": 0, "help": help_})
            continue
        if key == SWATCH:
            label, help_ = _MEANING[SWATCH]
            out.append({"key": key, "label": label, "group": "product",
                        "order": 900, "help": help_})
            continue
        m = _OTHER_RE.match(key)
        if m:
            n = int(m.group(1))
            out.append({"key": key, "label": "PT%d" % n, "group": "product",
                        "order": n,
                        "help": "Gallery image %d. Text, graphics and lifestyle "
                                "shots are allowed here." % n})
            continue
        m = _OFFER_RE.match(key)
        if m:
            n = int(m.group(2) or 0)
            out.append({"key": key, "label": "Offer image %s" % (n or "main"),
                        "group": "offer", "order": 1000 + n,
                        "help": "Shown against your OFFER rather than the "
                                "product itself. Rarely what you want."})
            continue
        # Anything else the schema defines -- compliance labels and whatever
        # Amazon adds next. Listed with its own title rather than guessed at or,
        # worse, hidden: a slot we do not recognise is still a slot they have.
        out.append({"key": key, "label": title or key, "group": "other",
                    "order": 2000,
                    "help": "Defined by this product type%s."
                            % (" — " + title if title else "")})
    out.sort(key=lambda s: (s["group"] != "product", s["order"], s["key"]))
    return out


def check_url(url):
    """Why Amazon could not fetch this image, or "" if it can.

    Amazon pulls the image from the URL we give it, over the open internet, from
    its own servers. A path only this app can resolve does not fail visibly -- it
    fails at Amazon's end, later, with an issue message that does not mention the
    URL at all.
    """
    u = str(url or "").strip()
    if not u:
        return "There is no image to send."
    if not URL_OK.match(u):
        return ("Amazon fetches the image itself, so it needs a public https:// "
                "address. This one is %s, which only this app can open. Upload it "
                "to the account's Drive folder first and send the Drive copy."
                % (u.split("?")[0][:60] or "a local path"))
    return ""


def refuse_slot(slot_key, made_as=""):
    """Why this image may not go in this slot, or "" if it may.

    A REFUSAL, not a warning: the app knows what it made each image FOR, because
    it files them that way -- the SKU folder root is main/concept work, and
    "secondary" and "aplus/..." are their own shelves.

    A secondary or A+ image is generated under rules that permit text, graphics,
    lifestyle scenes and props. Those are exactly the things Amazon suppresses a
    listing for when they appear on the MAIN image. So the app must not offer to
    send one there -- it would be handing over an image it had itself made
    unsuitable, and the listing would go down for it.

    The other direction is left open: a main image is generated under the
    strictest rules, so it is always acceptable as a PT image.
    """
    made = str(made_as or "").strip().lower()
    if slot_key != MAIN:
        return ""
    if made.startswith("aplus"):
        return ("This is an A+ module image. A+ images carry text and graphics, "
                "which Amazon suppresses listings for when they appear on the "
                "main image — so it cannot go in the main slot. Use a PT slot, "
                "or generate a main image for this product.")
    if made.startswith("secondary"):
        return ("The app generated this as a SECONDARY image, under rules that "
                "allow text, graphics and lifestyle scenes. Those are the things "
                "Amazon suppresses a listing for on the MAIN image, so it cannot "
                "go there. Send it to a PT slot, or generate a main image.")
    return ""


def warnings(slot_key, url, current_value="", is_variation_child=False):
    """Things worth saying before sending, that are not refusals.

    Separated from check_url on purpose: a refusal stops the send, a warning is
    something a person may knowingly go ahead with. Mixing the two either blocks
    legitimate work or lets a real mistake through in a list of noise.
    """
    out = []
    if current_value:
        out.append("This slot already has an image. Sending replaces it — the old "
                   "one is not kept anywhere on Amazon.")
    if slot_key == MAIN:
        out.append("As the MAIN image this must be on a pure white background "
                   "with no text, logos or props. Amazon suppresses listings "
                   "whose main image breaks that.")
    if slot_key == SWATCH and not is_variation_child:
        out.append("A swatch only appears in a variation picker, and this listing "
                   "is not part of a family — so it would have nowhere to show.")
    return out


def build_patch(slot_key, url, marketplace_id):
    """The patch operation for one slot. media_location is what Amazon requires."""
    return {"op": "replace", "path": "/attributes/" + slot_key,
            "value": [{"media_location": str(url).strip(),
                       "marketplace_id": marketplace_id}]}
