"""domain/image_story.py -- why each image is where it is.

    "show the aplus content and listing images to tell the user which is the 1st
     secondary image which is 2nd and which is third SAME FOr the modules and
     there should be a story or a logic behind every image that why it comes
     first second and third and so on"

A buyer does not study a carousel or an A+ page; they move through it, in order,
and stop the moment they are convinced or bored. So neither is a pile of
pictures -- both are a SEQUENCE, and each item answers the question the one
before it raises.

That sequence already existed in two places and was invisible in both:
dashboard._SECONDARY_ROLES knows what each image slot is for, and
ai_providers._APLUS_STORY tells the strategist to give every module a role. What
neither did was tell the PERSON which came first, or why.

This is the reasons, in one module, so the screen and the prompt cannot end up
telling different stories about the same set.

THE A+ ORDER IS A DEFAULT, NOT A LAW. The strategist is explicitly told to pick
the roles that suit the product -- "the right set for a supplement is not the
right set for a garden bench" -- so a page may legitimately skip roles or run
them in another order. What must never happen is a page with no order at all,
which is what a pile of modules each opening with the product name looks like.
"""

# The A+ page, top to bottom. Names match ai_providers._APLUS_STORY exactly, so
# a role the strategist returns can be looked up here without translation.
APLUS_STORY = [
    {"role": "open", "n": 1, "label": "Opening",
     "why": "What this is and who it is for, in one confident line. The reader "
            "has scrolled past the bullets and is still deciding whether to "
            "keep going."},
    {"role": "problem", "n": 2, "label": "The problem",
     "why": "The situation that made them look in the first place. Naming it is "
            "what turns a browser into somebody who wants an answer."},
    {"role": "answer", "n": 3, "label": "The answer",
     "why": "How this product solves it, concretely. It only lands once the "
            "problem above has been said out loud."},
    {"role": "proof", "n": 4, "label": "Proof",
     "why": "The evidence behind the claim just made. Proof placed before a "
            "claim answers a question nobody has asked yet."},
    {"role": "detail", "n": 5, "label": "The detail",
     "why": "The one thing a careful buyer inspects before paying. By here they "
            "want it and are checking it is good enough."},
    {"role": "use", "n": 6, "label": "In use",
     "why": "How it fits into their day. Moves it from a product they approve "
            "of to one they can see themselves owning."},
    {"role": "compare", "n": 7, "label": "Versus the alternative",
     "why": "Why this rather than the other tab they have open. Only worth "
            "answering once they have decided they want the category."},
    {"role": "close", "n": 8, "label": "The close",
     "why": "The reassurance that removes the last hesitation -- the guarantee, "
            "the fit, the support. Nothing new is introduced here."},
]

APLUS_BY_ROLE = {s["role"]: s for s in APLUS_STORY}


def aplus_step(role):
    """{n, label, why} for an A+ role, or a blank when the role is unknown.

    Never raises and never guesses: a strategist that invents a role name gets
    an unnumbered module rather than somebody else's explanation attached to it.
    """
    r = str(role or "").strip().lower()
    hit = APLUS_BY_ROLE.get(r)
    if not hit:
        return {"n": 0, "label": "", "why": "", "role": r}
    return dict(hit)


def secondary_steps(roles):
    """The secondary-image roles in the order they should be made.

    `roles` is dashboard._SECONDARY_ROLES. Passed in rather than imported so
    this module stays free of the app's import graph and can be tested alone.
    """
    out = []
    for key, spec in (roles or {}).items():
        out.append({"role": key,
                    "n": int(spec.get("order") or 0),
                    "present": spec.get("present", ""),
                    "why": spec.get("why", "")})
    out.sort(key=lambda s: (s["n"] or 99, s["role"]))
    return out


def numbered(picked, roles):
    """Number a CHOSEN set 1..n, keeping the canonical order between them.

    The canonical order runs 1-12, but nobody makes twelve secondary images --
    Amazon shows six or so. A set of four picked from across the twelve must be
    presented as 1, 2, 3, 4 in the right sequence, NOT as 2, 6, 9, 11: the
    number a person sees has to be the slot the image will occupy.

    Returns the picked roles in order, each with `slot` (its real position in
    the set) and `canonical` (where it sits in the full sequence, kept because
    it is what explains the ordering).
    """
    known = {s["role"]: s for s in secondary_steps(roles)}
    got = [known[r] for r in (picked or []) if r in known]
    got.sort(key=lambda s: (s["n"] or 99, s["role"]))
    out = []
    for i, s in enumerate(got, 1):
        d = dict(s)
        d["slot"] = i
        d["canonical"] = s["n"]
        out.append(d)
    return out
