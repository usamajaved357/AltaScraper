// The product page's pictures open full size, with arrows, and close again.
//
//     "I'm also not able to view the images inside the product detail page when
//      there is a draft in my app. I want to go to the image section inside that
//      product detail page draft item and click on the image to have a preview
//      at a bigger size. When I'm done previewing, I can cross that preview
//      screen. I also want to have arrows that can go right and left while I am
//      previewing the images inside the draft PDP."           (owner, 12 Oct 2026)
//
// WHAT IS GUARDED
//   * a slot's picture opens the SHARED viewer (ilPreview, listingimages.js) --
//     not a second lightbox -- at the full-size address, with the other filled
//     slots either side, in the grid's order;
//   * a strip picture opens from its magnifier, and that click does not also
//     fill a slot (its own click still does);
//   * an ×, a backdrop click and Escape close it; Escape does NOT reach the
//     product page behind it (it used to: both listen on the document and the
//     page's handler was registered first);
//   * the arrows and the arrow keys step and STOP at the ends, with "2 of 3";
//     one picture has no arrows;
//   * "Loading image…" until it arrives, a sentence (not a broken icon) when it
//     never does;
//   * it closes when the product page closes, on an account or marketplace
//     switch, and on a screen change.
//
// The REAL listingimages.js, pdp_images.js and core_util.js run here against a
// small stand-in for the DOM: enough HTML parsing to find elements by id and
// class, and a document whose keydown listeners run capture-first and honour
// stopPropagation the way a browser's do.
//
// Run: node test_pdp_image_preview.js
"use strict";
const fs = require("fs"), vm = require("vm"), path = require("path");

let fails = 0;
function check(label, got, want){
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if(!ok) fails++;
  console.log("  " + label.padEnd(72) + (ok ? "OK"
    : "FAIL\n      got  " + JSON.stringify(got) + "\n      want " + JSON.stringify(want)));
}
function truthy(label, got){ check(label, !!got, true); }
const read = p => fs.readFileSync(path.join(__dirname, p), "utf8");

/* The source of one named function, brace-matched. */
function fnBody(src, name){
  const m = new RegExp("\\bfunction\\s+" + name + "\\s*\\(").exec(src);
  if(!m) return "";
  let i = src.indexOf("{", m.index + m[0].length - 1);
  for(let j = i, depth = 0; j < src.length; j++){
    if(src[j] === "{") depth++;
    else if(src[j] === "}" && --depth === 0) return src.slice(i, j + 1);
  }
  return src.slice(i);
}

/* ---- a small DOM ---------------------------------------------------------- */
const decode = s => String(s).replace(/&quot;/g, '"').replace(/&#39;/g, "'")
  .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");

let DOC = null;
function El(tag, attrs){
  const el = {
    tagName: String(tag).toUpperCase(), attrs: {}, style: {}, kids: [],
    parentNode: null, listeners: {}, _text: "", _html: "",
    complete: false, naturalWidth: 0,
    classList: null,
    get id(){ return this.attrs.id || ""; },
    set id(v){ this.attrs.id = String(v); },
    get src(){ return this.attrs.src || ""; },
    set src(v){ this.attrs.src = String(v); this.complete = false; this.naturalWidth = 0; },
    get alt(){ return this.attrs.alt || ""; },
    set alt(v){ this.attrs.alt = String(v); },
    get textContent(){ return this._text; },
    set textContent(v){ this._text = String(v); },
    get isConnected(){ let n = this; while(n){ if(n === DOC.body) return true; n = n.parentNode; } return false; },
    setAttribute(k, v){ this.attrs[k] = String(v); if(k === "class") syncClass(this); },
    getAttribute(k){ return k in this.attrs ? this.attrs[k] : null; },
    hasAttribute(k){ return k in this.attrs; },
    addEventListener(t, fn){ (this.listeners[t] = this.listeners[t] || []).push(fn); },
    removeEventListener(t, fn){ this.listeners[t] = (this.listeners[t] || []).filter(f => f !== fn); },
    fire(t, ev){ (this.listeners[t] || []).slice().forEach(f => f(ev || {target: this})); },
    appendChild(c){ c.parentNode = this; this.kids.push(c); return c; },
    removeChild(c){ this.kids = this.kids.filter(k => k !== c); c.parentNode = null; return c; },
    remove(){ if(this.parentNode) this.parentNode.removeChild(this); },
    focus(){ DOC.activeElement = this; },
    all(){ const out = []; this.kids.forEach(k => { out.push(k); out.push(...k.all()); }); return out; },
    querySelector(sel){ return this.all().find(e => matches(e, sel)) || null; },
    querySelectorAll(sel){ return this.all().filter(e => matches(e, sel)); },
    get innerHTML(){ return this._html; },
    set innerHTML(h){
      this._html = String(h);
      this.kids.forEach(k => { k.parentNode = null; });
      this.kids = [];
      // Flat: every opening tag becomes a child. Nesting does not matter to
      // anything asked of this page -- elements are found by id and class.
      const re = /<([a-zA-Z][\w-]*)((?:\s+[\w:-]+(?:="[^"]*")?)*)\s*\/?>/g;
      let m;
      while((m = re.exec(this._html))){
        const a = {};
        (m[2].match(/[\w:-]+(?:="[^"]*")?/g) || []).forEach(p => {
          const eq = p.indexOf("=");
          if(eq < 0) a[p] = ""; else a[p.slice(0, eq)] = decode(p.slice(eq + 2, -1));
        });
        const kid = this.appendChild(El(m[1], a));
        // Its own text: what follows the tag up to the next one.
        const rest = this._html.slice(re.lastIndex);
        kid._text = decode(rest.slice(0, rest.indexOf("<") < 0 ? rest.length : rest.indexOf("<")));
      }
    },
  };
  const cls = new Set();
  el.classList = {
    add: (...c) => { c.forEach(x => cls.add(x)); el.attrs["class"] = [...cls].join(" "); },
    remove: (...c) => { c.forEach(x => cls.delete(x)); el.attrs["class"] = [...cls].join(" "); },
    toggle: (c, on) => { const v = on === undefined ? !cls.has(c) : !!on;
                         v ? cls.add(c) : cls.delete(c); el.attrs["class"] = [...cls].join(" "); return v; },
    contains: c => cls.has(c),
  };
  el._cls = cls;
  Object.keys(attrs || {}).forEach(k => el.setAttribute(k, attrs[k]));
  // An inline style attribute becomes the style object, as a browser would.
  if(attrs && attrs.style) attrs.style.split(";").forEach(d => {
    const i = d.indexOf(":"); if(i > 0) el.style[d.slice(0, i).trim()] = d.slice(i + 1).trim();
  });
  return el;
}
function syncClass(el){
  el._cls.clear();
  String(el.attrs["class"] || "").split(/\s+/).filter(Boolean).forEach(c => el._cls.add(c));
}
function matches(el, sel){
  // "#a .b" -- only the last part matters here: everything is under #ilpreview
  // or the slot grid, and each test asks about one of them at a time.
  const last = sel.trim().split(/\s+/).pop();
  if(last[0] === "#") return el.id === last.slice(1);
  if(last[0] === ".") return el.classList.contains(last.slice(1));
  return el.tagName === last.toUpperCase();
}

function makeDoc(){
  const body = El("body");
  const keyListeners = [];        // {fn, capture}
  const doc = {
    body, activeElement: body,
    createElement: t => El(t),
    getElementById: id => body.all().find(e => e.id === id) || null,
    querySelector: sel => body.querySelector(sel),
    querySelectorAll: sel => body.querySelectorAll(sel),
    addEventListener(t, fn, capture){
      if(t === "keydown") keyListeners.push({fn, capture: !!capture});
    },
    removeEventListener(t, fn, capture){
      if(t !== "keydown") return;
      const i = keyListeners.findIndex(l => l.fn === fn && l.capture === !!capture);
      if(i >= 0) keyListeners.splice(i, 1);
    },
    keyListeners,
    // A key pressed with focus on the page: the document's capture listeners,
    // then (unless one stopped it) its bubbling ones -- in the order added.
    key(k){
      const ev = {key: k, target: doc.activeElement || body, defaultPrevented: false, _stop: false,
                  preventDefault(){ this.defaultPrevented = true; },
                  stopPropagation(){ this._stop = true; }};
      const list = keyListeners.slice();
      list.filter(l => l.capture).forEach(l => { if(!ev._stop) l.fn(ev); });
      list.filter(l => !l.capture).forEach(l => { if(!ev._stop) l.fn(ev); });
      return ev;
    },
  };
  return doc;
}

/* ---- the real files, in a sandbox --------------------------------------- */
function load(){
  DOC = makeDoc();
  const opened = [];
  const ctx = {
    console, document: DOC, setTimeout: () => 0, clearTimeout(){},
    fetch: () => new Promise(() => {}),
    toast(){}, acctId: () => "acct-A",
    window: null, opened,
  };
  ctx.window = ctx;
  ctx.open = (u) => { opened.push(u); };
  vm.createContext(ctx);
  // jsArg lives in users.js, which does a great deal at load; only it is taken.
  vm.runInContext("function jsArg" + read("static/js/users.js").match(/function jsArg(\(s\)\{[\s\S]*?\n\})/)[1],
                  ctx, {filename: "users.js#jsArg"});
  ["static/js/core_util.js", "static/js/listingimages.js", "static/js/pdp_images.js"]
    .forEach(f => vm.runInContext(read(f), ctx, {filename: f}));
  return ctx;
}

// Run an inline handler the way the browser would, with `event` to hand.
function runHandler(ctx, el, attr){
  const ev = {stopped: false, stopPropagation(){ this.stopped = true; }};
  ctx.event = ev;
  vm.runInContext(el.getAttribute(attr || "onclick"), ctx);
  delete ctx.event;
  return ev;
}

const A = "https://img.example/drafts/main%20shot.jpg?v=3";
const B = "https://m.media-amazon.com/images/I/71live.jpg";
const C = "/media/_acct/a/SKU-1/gen.png";

function draftPage(ctx, attrs, slots){
  const ROW = {sku: "SKU-1", product_type: "SQUEEGEE", attributes: attrs};
  ctx.pdpRow = () => ROW;
  // PDPI is a top-level `let`: reachable by name inside the sandbox, not as a
  // property of it -- so the object itself is fetched and changed in place.
  const P = vm.runInContext("PDPI = _pdpiEmpty('SKU-1','SQUEEGEE'); PDPI", ctx);
  P.checked = true;
  P.slots = slots;
  const host = El("div");
  host.innerHTML = ctx._pdpiSlotsHtml();
  return host;
}
const SLOTS = () => [
  {key: "main_product_image_locator", label: "Main", current: ""},
  {key: "other_product_image_locator_1", label: "PT1", current: B},   // only on Amazon
  {key: "other_product_image_locator_2", label: "PT2", current: ""},
  {key: "other_product_image_locator_3", label: "PT3", current: ""},  // empty
  {key: "swatch_product_image_locator", label: "Swatch", current: ""},
];
const ATTRS = () => ({main_product_image_locator: A, other_product_image_locator_2: C});

/* ========================================================================== */
console.log("=== a slot's picture opens the shared viewer ===");
{
  const ctx = load();
  const host = draftPage(ctx, ATTRS(), SLOTS());
  const pics = host.querySelectorAll("img").filter(i => /pdpImgPreviewSlot\(/.test(i.getAttribute("onclick") || ""));
  check("every FILLED slot's picture is clickable, and only those", pics.length, 3);
  check("  at the full-size address, not a thumbnail", pics.map(p => p.src), [A, B, C]);
  truthy("  reachable from the keyboard (role=button, tabindex=0)",
         pics.every(p => p.getAttribute("role") === "button" && p.getAttribute("tabindex") === "0"));
  truthy("  and the × that clears a slot is still its own button",
         /onclick="pdpImgClear\(/.test(ctx._pdpiSlotsHtml()));

  // A bubbling Escape listener registered BEFORE the viewer opens -- where the
  // product page's (pdp.js) and escape.js's sit.
  let pageClosed = 0;
  DOC.addEventListener("keydown", ev => { if(ev.key === "Escape" && !ev.defaultPrevented) pageClosed++; });

  runHandler(ctx, pics[1]);                              // PT01, Amazon's picture
  const ov = DOC.getElementById("ilpreview");
  truthy("clicking it opens the viewer over the page", ov && ov.isConnected);
  check("  a dialog, named", [ov.getAttribute("role"), ov.getAttribute("aria-label")],
        ["dialog", "Image preview"]);
  const img = DOC.getElementById("ilpreviewimg");
  check("  showing the picture that was clicked", img.src, B);
  check("  as 2 of the 3 filled slots", DOC.getElementById("ilpreviewcount").textContent, "2 of 3");
  check("  named by its slot", DOC.getElementById("ilpreviewname").textContent, "PT01 · 71live.jpg");
  const x = DOC.getElementById("ilpreviewx");
  truthy("there is an × to close it, with a name a screen reader can say",
         x && /ilPreviewClose\(\)/.test(x.getAttribute("onclick")) && x.getAttribute("aria-label"));
  truthy("  and focus is on it", DOC.activeElement === x);
  check("two arrows", DOC.querySelectorAll("#ilpreview .ilnav").length, 2);

  console.log("\n=== loading, loaded, failed ===");
  const msg = DOC.getElementById("ilpreviewmsg");
  check("while it loads: a message, and no half-drawn picture",
        [msg.style.display, msg.textContent, img.style.display], ["", "Loading image…", "none"]);
  img.complete = true; img.naturalWidth = 1500; img.fire("load");
  check("once it arrives: the picture, and no message", [img.style.display, msg.style.display], ["", "none"]);

  console.log("\n=== the arrows step, and stop at the ends ===");
  DOC.key("ArrowRight");
  check("right arrow key: the next filled slot", [img.src, DOC.getElementById("ilpreviewcount").textContent], [C, "3 of 3"]);
  check("  shown as loading again until it arrives", [img.style.display, msg.textContent], ["none", "Loading image…"]);
  truthy("  the next arrow is dimmed at the last picture", DOC.querySelector("#ilpreview .ilnext").classList.contains("off"));
  DOC.key("ArrowRight");
  check("  and pressing it again stays put (no wrap)", img.src, C);
  img.fire("error");
  check("a picture that cannot be fetched says so, instead of a broken icon",
        [img.style.display, msg.style.display, /could not be loaded/.test(msg.textContent), msg.classList.contains("bad")],
        ["none", "", true, true]);
  runHandler(ctx, DOC.querySelector("#ilpreview .ilprev"));
  runHandler(ctx, DOC.querySelector("#ilpreview .ilprev"));
  check("the on-screen left arrow steps back to the first", [img.src, DOC.getElementById("ilpreviewcount").textContent], [A, "1 of 3"]);
  truthy("  where the previous arrow is dimmed", DOC.querySelector("#ilpreview .ilprev").classList.contains("off"));
  DOC.key("ArrowLeft");
  check("  and stays put", img.src, A);
  check("  Download follows the picture", /main%20shot\.jpg/.test(DOC.getElementById("ilpreviewdl").getAttribute("onclick")), true);

  console.log("\n=== Escape closes the viewer, not the page behind it ===");
  const ev = DOC.key("Escape");
  check("the viewer is gone", DOC.getElementById("ilpreview"), null);
  check("  the product page's Escape handler never saw the key", pageClosed, 0);
  truthy("  and the key is marked as handled", ev.defaultPrevented);
  check("  its key listener is removed with it", DOC.keyListeners.length, 1);
  DOC.key("Escape");
  check("the next Escape reaches the page again", pageClosed, 1);
}

console.log("\n=== the × and the backdrop close it; the picture itself does not ===");
{
  const ctx = load();
  const host = draftPage(ctx, ATTRS(), SLOTS());
  const pic = host.querySelectorAll("img").find(i => /pdpImgPreviewSlot/.test(i.getAttribute("onclick") || ""));
  runHandler(ctx, pic);
  const ov = DOC.getElementById("ilpreview");
  ov.fire("click", {target: DOC.getElementById("ilpreviewimg")});
  truthy("clicking the picture leaves it open", DOC.getElementById("ilpreview"));
  ov.fire("click", {target: ov});
  check("clicking the dark backdrop closes it", DOC.getElementById("ilpreview"), null);
  runHandler(ctx, pic);
  runHandler(ctx, DOC.getElementById("ilpreviewx"));
  check("the × closes it", DOC.getElementById("ilpreview"), null);
  check("  leaving no key listener behind", DOC.keyListeners.length, 0);
}

console.log("\n=== one picture: no arrows ===");
{
  const ctx = load();
  const host = draftPage(ctx, {main_product_image_locator: A},
    SLOTS().map(s => Object.assign(s, {current: ""})));
  const pics = host.querySelectorAll("img").filter(i => /pdpImgPreviewSlot/.test(i.getAttribute("onclick") || ""));
  check("one filled slot, one clickable picture", pics.length, 1);
  runHandler(ctx, pics[0]);
  check("no arrows and no counter",
        [DOC.querySelectorAll("#ilpreview .ilnav").length, DOC.getElementById("ilpreviewcount")], [0, null]);
  DOC.key("ArrowRight");
  check("  and the arrow keys do nothing", DOC.getElementById("ilpreviewimg").src, A);
  truthy("  the × is still there", DOC.getElementById("ilpreviewx"));
}

console.log("\n=== no pictures: nothing to open ===");
{
  const ctx = load();
  const host = draftPage(ctx, {}, SLOTS().map(s => Object.assign(s, {current: ""})));
  check("an empty slot has no picture to click", host.querySelectorAll("img").length, 0);
  ctx.pdpImgPreviewSlot("main_product_image_locator");
  check("  and asking for one opens nothing", DOC.getElementById("ilpreview"), null);
}

console.log("\n=== a strip picture opens from its magnifier, and still fills on click ===");
{
  const ctx = load();
  draftPage(ctx, ATTRS(), SLOTS());
  const P = vm.runInContext("PDPI", ctx);
  P.comp = {ebay: ["https://e/1.jpg", "https://e/2.jpg"], amazon: [], ebay_error: "", amazon_error: ""};
  P.compTab = "ebay";
  const strip = El("div");
  strip.innerHTML = ctx._pdpiStripHtml();
  const thumbs = strip.querySelectorAll(".pdpi-thumb");
  const zooms = strip.querySelectorAll(".pdpi-zoom");
  check("every strip picture has a magnifier", [thumbs.length, zooms.length], [2, 2]);
  truthy("  clicking the picture still fills the next empty slot",
         thumbs.every(t => /^pdpImgFillNext\(/.test(t.getAttribute("onclick"))));
  truthy("  the magnifier has a name a screen reader can say", zooms.every(z => z.getAttribute("aria-label")));
  const ev = runHandler(ctx, zooms[1]);
  truthy("  and its click stops before it reaches the picture", ev.stopped);
  check("it opens the viewer on that picture, as 2 of the tab's 2",
        [DOC.getElementById("ilpreviewimg").src, DOC.getElementById("ilpreviewcount").textContent],
        ["https://e/2.jpg", "2 of 2"]);
}

console.log("\n=== it never outlives the page, the account or the screen ===");
{
  const PDP = read("static/js/pdp.js"), SS = read("static/js/screenstate.js"),
        SH = read("static/js/shell.js");
  truthy("closing the product page closes it (pdpClose)", /ilPreviewClose\(\)/.test(fnBody(PDP, "pdpClose")));
  truthy("an account or marketplace switch closes it (screenForgetAll)",
         /ilPreviewClose\(\)/.test(fnBody(SS, "screenForgetAll")));
  truthy("a screen change closes it (navTo)", /ilPreviewClose\(\)/.test(fnBody(SH, "navTo")));
  const ctx = load();
  ctx.ilPreviewClose();
  check("  and closing when nothing is open is harmless", DOC.getElementById("ilpreview"), null);
}

console.log("\n=== one viewer, not two (Rule 12) ===");
{
  const IMG = read("static/js/pdp_images.js");
  truthy("the product page calls the library's viewer", /ilPreview\(it\.url, it\.name, list, at\)/.test(IMG));
  check("  and builds no overlay of its own", /createElement\(/.test(IMG), false);
  check("the slot grid and the viewer read one slot-picture rule",
        (IMG.match(/(?<!function )_pdpiSlotUrl\(s, assigned\)/g) || []).length, 2);
}

console.log("\nFAILURES: " + fails);
process.exit(fails ? 1 : 0);
