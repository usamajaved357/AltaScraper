# SOURCING VIABILITY CHECK — Complete Rules

Paste this entire file as a Claude Code prompt.

---

SOURCING VIABILITY CHECK — catch products where Amazon will 
request docs we can't provide, BEFORE we list them

PROBLEM: An electric patio heater was not gated or restricted. 
We listed it freely. Months later Amazon asked for BS EN 60335 
safety docs we don't have. This is not a restricted products 
problem — it's a "can we fulfil the documentation obligations" 
problem. As arbitrage/resellers, we almost never have 
manufacturer safety documentation.

BUILD: A sourcing viability checker that runs during generation.
New function: check_sourcing_viability(title, bullets, 
product_type, category, marketplace)
Returns: list of matched rules with rule name, trigger, docs 
Amazon will request, risk level, plain English warning.

Put rules in sourcing_viability_rules.json so new rules can 
be added without code changes.

Wire into generation path AFTER restricted products check, 
BEFORE sheet write. Status effect: WARN in notes, never HOLD. 
Warning: "SOURCING RISK [{rule}]: Amazon will likely request 
{docs}. As a reseller you probably cannot provide these."

Also wire into Shape 1 "Check product" modal.

## RULES — 15 categories

RULE 1: MAINS_ELECTRICAL
  Trigger: (electric OR electrical OR mains OR plug-in OR 
  corded OR 240v OR 230v OR 110v) AND any appliance noun 
  (heater, fan, dryer, iron, blender, charger, lamp, cooker, 
  fryer, steamer, kettle, toaster, straightener, curler, 
  shaver, trimmer, vacuum, hoover, drill, grinder, saw, 
  sander, welder, compressor, air purifier, dehumidifier, 
  humidifier, dishwasher, washing machine, microwave, oven, 
  hob, extractor, heat gun, pressure washer)
  OR: wattage claim >= 500W in title/bullets
  OR: "UK plug" OR "3-pin plug" OR "BS 1363"
  Docs UK: BS EN 60335 product-specific test report, UKCA DoC, 
  UK Responsible Person, BS 1363 plug compliance, EMC test
  Docs US: UL/ETL/CSA safety cert, FCC if wireless
  Risk: HIGH
  Reason: OPSS actively pulls non-compliant electrical products 
  from Amazon UK. Heaters, chargers, and hair tools are the 
  most enforced subcategories.

RULE 2: LOW_VOLTAGE_ELECTRICAL
  Trigger: (USB charger OR power bank OR phone charger OR 
  laptop charger OR adapter OR adaptor OR power supply OR 
  LED driver OR LED strip OR fairy lights OR string lights OR 
  LED floodlight OR USB hub OR docking station OR USB-C cable)
  Docs UK: UKCA DoC, LVD test report, EMC test, UK RP
  Docs US: FCC authorization, UL listing
  Risk: HIGH
  Reason: USB chargers and LED lights are OPSS enforcement 
  priorities. Even low-voltage products need EMC + LVD testing.

RULE 3: CHILDREN_PRODUCT
  Trigger: product for children under 14 (toy, baby product, 
  nursery, kids furniture, children's costume, play mat, 
  teething, dummy, pacifier, baby monitor, highchair, car seat, 
  pushchair, pram, baby walker, baby gate, cot, crib, Moses 
  basket) — NOT children's books/media
  Docs UK: EN 71 toy safety test (parts 1-3 minimum), UKCA, 
  age grading, small parts warning, UK RP
  Docs US: CPC, CPSIA lead/phthalate testing, ASTM F963, 
  tracking label
  Risk: HIGH
  Reason: Amazon now requires annual testing verification for 
  all children's toys. Proactive enforcement expanding.

RULE 4: SKIN_CONTACT_COSMETIC
  Trigger: product applied to skin (cream, lotion, serum, oil 
  for skin, soap, shampoo, conditioner, face mask cosmetic, 
  lip balm, deodorant, sunscreen, moisturiser, moisturizer, 
  body wash, cleanser, toner, exfoliant, hair dye, nail polish, 
  perfume, aftershave, bath bomb, essential oil for skin)
  Docs UK: CPSR (Cosmetic Product Safety Report), PIF (Product 
  Information File), SCPN notification, full INCI ingredient 
  list, UK RP
  Docs US: FDA cosmetic registration (MoCRA 2022), ingredient 
  listing, adverse event reporting capability
  Risk: HIGH
  Reason: Cosmetics regulation requires a qualified safety 
  assessor's report. Resellers cannot produce this.

RULE 5: FOOD_GROCERY
  Trigger: product is food or drink (food, snack, biscuit, 
  chocolate, candy, tea, coffee, spice, sauce, seasoning, 
  cooking oil, flour, sugar, protein bar, energy drink, juice, 
  supplement powder edible, dried fruit, nuts edible, honey, 
  jam, spread, cereal)
  Docs UK: Food Safety Act compliance, allergen declaration, 
  nutritional labeling, lot/batch traceability, FSA registration
  Docs US: FDA facility registration, FDA prior notice for 
  imports, nutrition facts label, FSMA compliance
  Risk: HIGH
  Reason: Food requires full supply chain traceability and 
  allergen documentation. Cannot be sourced without manufacturer 
  cooperation.

RULE 6: FOOD_CONTACT_MATERIAL
  Trigger: product touches food during use (chopping board, 
  food container, water bottle, lunch box, cooking utensil, 
  baking tray, food wrap, silicone mould baking, drinking 
  straw reusable, coffee mug, wine glass, plate, bowl ceramic, 
  food storage, thermos, flask drink, ice cube tray, cake tin)
  Docs UK: Food contact material declaration (UK equivalent of 
  EC 1935/2004), migration testing if plastic/silicone/melamine
  Docs US: FDA 21 CFR compliance for food contact
  Risk: MEDIUM
  Reason: Amazon requests REACH + food contact test reports, 
  especially for Chinese-origin silicone/melamine kitchenware.

RULE 7: BATTERY_POWERED
  Trigger: contains lithium battery (lithium, li-ion, 
  rechargeable battery, mAh reference over 100, 18650, 21700, 
  lipo, lithium polymer, built-in battery, internal battery)
  Docs: UN38.3 battery test summary, MSDS/SDS, hazmat shipping 
  classification, battery composition disclosure
  Risk: MEDIUM
  Reason: Required for FBA acceptance. Amazon requests for MFN 
  listings during compliance sweeps.

RULE 8: PPE_SAFETY
  Trigger: product claimed as protective (safety goggles, hard 
  hat, ear defenders, hi-vis vest, safety boots, dust mask, 
  respirator, welding helmet, face shield, safety gloves, 
  knee pads protective, back support belt, fall harness)
  Docs UK: PPE Regulation 2016/425 Type Examination, UKCA, DoC, 
  Notified Body certificate, UK RP
  Docs US: OSHA compliance, ANSI standards certification
  Risk: HIGH
  Reason: PPE requires Notified Body involvement for Category 
  II and III. Resellers cannot obtain this.

RULE 9: JEWELLERY_ACCESSORIES
  Trigger: jewellery, jewelry, necklace, bracelet, ring, 
  earring, piercing, anklet, brooch, pendant, bangle, 
  watch band, costume jewellery
  Docs UK: REACH heavy metals test (lead, cadmium, nickel 
  release), UK Hallmarking Act if precious metals
  Docs US: CPSIA lead limits for children's jewelry, 
  California Prop 65 lead/cadmium
  Risk: MEDIUM
  Reason: Amazon requests REACH test reports for jewellery, 
  especially for nickel release and lead/cadmium content.

RULE 10: TEXTILES_CLOTHING
  Trigger: clothing, t-shirt, dress, trousers, jacket, coat, 
  hoodie, underwear, socks, scarf, gloves clothing, hat 
  clothing, swimwear, activewear, uniform, workwear, fabric, 
  bedding, duvet, pillow, curtains, towel, rug, carpet, 
  upholstery fabric
  Docs UK: Textile Products (Labelling and Fibre Composition) 
  Regulations fibre content labeling, REACH/azo dyes test, 
  flammability for nightwear/children's clothing
  Docs US: FTC Textile Fiber Products Identification Act, 
  Care Labeling Rule, CPSIA for children's apparel, 
  flammability standards 16 CFR 1610/1615/1616
  Risk: MEDIUM
  Reason: Amazon can request REACH azo dye test reports and 
  fibre composition verification. Children's clothing faces 
  additional flammability testing requirements.

RULE 11: PRESSURE_EQUIPMENT
  Trigger: pressure cooker, pressure washer, air compressor, 
  pressure vessel, autoclave, pneumatic tool, gas cylinder, 
  CO2 canister
  Docs UK: Pressure Equipment (Safety) Regulations 2016, 
  UKCA, conformity assessment, UK RP
  Risk: HIGH
  Reason: Pressure equipment requires conformity assessment 
  by a UK Approved Body for higher categories.

RULE 12: GAS_APPLIANCE
  Trigger: gas heater, gas cooker, gas hob, gas BBQ, gas fire, 
  propane heater, butane heater, camping stove gas, gas 
  regulator, LPG appliance
  Docs UK: Gas Appliances Regulation, UKCA, test to BS EN 498 
  or product-specific standard, UK RP
  Risk: HIGH
  Reason: Gas appliances require type examination. Selling 
  non-certified gas appliances is a criminal offence in the UK.

RULE 13: MACHINERY
  Trigger: chainsaw, lathe, bench saw, table saw, circular saw 
  power, band saw, milling machine, CNC machine, generator 
  petrol, log splitter, cement mixer, woodchipper
  Docs UK: Supply of Machinery (Safety) Regulations, UKCA, 
  DoC, UK RP, instructions in English
  Docs US: OSHA compliance, ANSI standards
  Risk: HIGH
  Reason: Machinery directive requires conformity assessment 
  and comprehensive risk assessment documentation.

RULE 14: CHEMICALS_CLEANING
  Trigger: cleaning product chemical, bleach, disinfectant, 
  detergent, drain cleaner, oven cleaner, paint, varnish, 
  adhesive, solvent, stain remover, rust remover, descaler, 
  pool chemicals, anti-freeze
  Docs UK: CLP classification and labeling, SDS (Safety Data 
  Sheet), UK REACH registration if >1 tonne, UFI code
  Docs US: EPA registration if pesticidal claim, SDS, GHS 
  labeling
  Risk: HIGH
  Reason: Chemical products require CLP hazard classification, 
  proper GHS labeling, and SDS from the manufacturer. 
  Pesticidal claims trigger EPA/HSE registration.

RULE 15: SPORTING_FITNESS_EQUIPMENT
  Trigger: gym equipment, weight bench, treadmill, exercise 
  bike, rowing machine, pull-up bar, punch bag, trampoline, 
  climbing harness, bicycle, e-bike, electric scooter, 
  skateboard electric, hoverboard, helmet sport, life jacket, 
  buoyancy aid
  Docs UK: GPSR 2005 compliance, product-specific EN standards, 
  UKCA where applicable (e-bikes, helmets, life jackets = PPE), 
  UK RP
  Risk: MEDIUM (HIGH for e-bikes, hoverboards, helmets, 
  life jackets)
  Reason: Amazon requests documentation for gym equipment 
  under GPSR. Hoverboards/e-bikes have specific battery and 
  electrical safety requirements. Helmets and life jackets 
  are PPE.

## IMPLEMENTATION NOTES

- Trigger matching should use the same corroborated keyword 
  pattern as the compliance checker: common words (fan, iron, 
  light, oil, plate, ring, net, bar) must corroborate with a 
  second signal. "Curling iron" triggers, "iron supplement" 
  does not. "Engagement ring" triggers, "ring binder" does not.
- Each rule has an EXCLUDE list to prevent false positives:
  - MAINS_ELECTRICAL excludes: "electric blue", "electric 
    guitar strings", "electric car accessories" (non-mains)
  - CHILDREN_PRODUCT excludes: "adult costume", books, media
  - FOOD_CONTACT_MATERIAL excludes: decorative plates, 
    display-only items
  - JEWELLERY excludes: jewellery box, jewellery stand, 
    jewellery cleaning
  - TEXTILES excludes: fabric paint, sewing patterns, buttons
  - SPORTING excludes: sports bag, sports water bottle
- Risk levels: HIGH = Amazon actively enforces, docs almost 
  certainly requested. MEDIUM = Amazon may request during 
  random audits. LOW = unlikely but possible.
- Multiple rules can match one product. A baby's silicone 
  teething toy triggers CHILDREN_PRODUCT + FOOD_CONTACT_MATERIAL.
- The warning should list ALL matched rules and their docs.

Test cases — must trigger:
  "2000W Electric Patio Heater IP34" → MAINS_ELECTRICAL
  "USB-C Fast Charger 65W GaN" → LOW_VOLTAGE_ELECTRICAL
  "Wooden Toy Train Set Ages 3+" → CHILDREN_PRODUCT
  "Hyaluronic Acid Face Serum 30ml" → SKIN_CONTACT_COSMETIC
  "Silicone Baking Mat Non-Stick" → FOOD_CONTACT_MATERIAL
  "Sterling Silver Necklace Pendant" → JEWELLERY_ACCESSORIES
  "Men's Cotton Polo Shirt" → TEXTILES_CLOTHING
  "Camping Gas Stove Portable" → GAS_APPLIANCE
  "Chainsaw 16 inch Petrol" → MACHINERY
  "Oven Cleaner Spray 500ml" → CHEMICALS_CLEANING
  "Adjustable Weight Bench" → SPORTING_FITNESS

Test cases — must NOT trigger:
  "Phone Case Silicone Clear" → clean
  "Wall Art Canvas Print" → clean
  "Garden Hose Reel 30m" → clean
  "Book Stand Holder Desktop" → clean
  "Patio Heater Cover Waterproof" → clean (cover, not heater)
  "Iron Supplement Tablets" → clean (not a clothes iron)
  "Ring Binder A4 Folder" → clean (not jewellery)

Nothing pushed, model unchanged.
