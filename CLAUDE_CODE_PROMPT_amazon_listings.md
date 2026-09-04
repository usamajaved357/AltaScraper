There are THREE different product detail views in the app. 
Only ONE should exist — the PDP overlay we're redesigning.

1. Full-page PDP overlay at /listing/{sku} — KEEP THIS, redesign it
2. Right-side drawer — REMOVE (already requested)
3. "Optimize live listing" modal dialog — REMOVE

The "Optimize live listing" modal appears when clicking on some 
live listings from the listings page. It shows Amazon warnings, 
a "Suggest fixes with AI" button, and a "Custom AI Rewrite" form.

Find what triggers this modal (search for "Optimize live listing" 
or "optimize" in the JS files) and replace it with the PDP overlay. 
When a user clicks on ANY listing — draft or live — it should 
always open the same PDP overlay. No modals, no drawers, no 
separate optimize dialogs.

The AI rewrite and Amazon warnings features currently in this 
modal should move to the PDP overlay:
- Amazon warnings → show on the Safety & Compliance tab
- "Suggest fixes with AI" → this is the Auto-fix button already 
  in the PDP top bar
- "Custom AI Rewrite" → move to the Product Details tab as an 
  action, or to the sidebar under Quick Actions as "Ask Claude" 
  (which already exists there)

Trace every code path that opens any product detail view and 
make them ALL open the PDP overlay. List every trigger you find 
so we can verify nothing still fires the old UIs.

Two related issues:

1. MOST LIVE LISTINGS OPEN THE WRONG UI

Most live listings open the "Optimize live listing" modal instead 
of the PDP overlay. Only listings that were originally created by 
this app (through the generator) open the PDP overlay. Listings 
that were synced from Amazon or existed before the app open the 
modal.

This is probably because the app checks whether it "owns" the 
listing — if it has a draft row in the database, it opens the PDP. 
If it doesn't (catalogue-only listing from Sync), it opens the 
optimize modal.

Fix: ALL listings open the PDP overlay regardless of origin. A 
listing synced from Amazon is still a listing you manage. The PDP 
should work for both:
- Listings created by the app (has draft data + Amazon data)
- Listings synced from Amazon (has Amazon data only, no draft)

For synced-only listings, the PDP should show Amazon's current 
attribute data as the input values (from the catalogue/summaries), 
not empty fields. The user can then edit and push changes via 
putListingsItem.

Trace the click handler on listing rows — find the condition that 
decides "open PDP" vs "open optimize modal" and make it always 
open the PDP.


2. CAN'T CHANGE HANDLING TIME ON INDIVIDUAL LISTINGS

The handling time field is not editable on listings that the app 
didn't create. The editable handling time input only appears for 
listings with a draft row in the database.

Fix: handling time should be editable on ALL live listings, 
regardless of whether the app created them. For catalogue-only 
listings (synced from Amazon, no draft row):
- Read the current handling time from Amazon's listing data
- Show it as an editable field
- When changed, push via putListingsItem (same as it does for 
  app-created listings)
- Save locally by creating a minimal row in the store if one 
  doesn't exist, or by writing to a separate field

The user manages ALL their Amazon listings through this app, not 
just the ones the app generated. Every listing should have the 
same editing capabilities.
