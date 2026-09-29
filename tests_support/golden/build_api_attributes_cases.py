"""Golden cases for build_api_attributes (docs/plans/build-api-attributes.md, B0).

Hand-built product-type schemas (no real Amazon schema is kept in the repo, and
none may be read from anyone's data), designed to drive the builder through its
phases: text, brand, model/part, offer, images, identifiers (Rule 1), dimensions,
the flat attribute mapping, batteries / hazmat / GHS, required backfill, minimal
mode and cleanup. Each case is run on UK and US marketplaces, minimal mode off
and on. The recorded output is the payload as it is TODAY; a refactor must
reproduce it byte for byte.
"""
import json

UK = "A1F83G8C2ARO7P"
US = "ATVPDKIKX0DER"


def _loc(extra=None):
    """A localised text field: [{value, language_tag, marketplace_id}]."""
    p = {"value": {"type": "string"}, "language_tag": {"type": "string"},
         "marketplace_id": {"type": "string"}}
    p.update(extra or {})
    return {"type": "array", "items": {"type": "object", "properties": p}}


def _plain(extra=None):
    """A non-localised field: [{value, marketplace_id}]."""
    p = {"value": {"type": "string"}, "marketplace_id": {"type": "string"}}
    p.update(extra or {})
    return {"type": "array", "items": {"type": "object", "properties": p}}


def _enum(values):
    return _plain({"value": {"type": "string", "enum": list(values)}})


def _bool():
    return _plain({"value": {"type": "boolean"}})


def _num():
    return _plain({"value": {"type": "number"}})


def _dim(parts):
    props = {k: {"type": "object", "properties": {
        "value": {"type": "number"}, "unit": {"type": "string",
                                               "enum": ["centimeters", "inches", "millimeters"]}}}
             for k in parts}
    props["marketplace_id"] = {"type": "string"}
    return {"type": "array", "items": {"type": "object", "properties": props}}


def _weight():
    return _plain({"value": {"type": "number"},
                   "unit": {"type": "string", "enum": ["grams", "kilograms", "pounds"]}})


TEXT = {k: _loc() for k in ("item_name", "bullet_point", "product_description",
                            "generic_keyword", "brand", "manufacturer",
                            "special_feature", "material", "color", "included_components",
                            "warranty_description", "item_type_keyword")}
BASIC = dict(TEXT, **{
    "condition_type": _enum(["new_new", "used_like_new"]),
    "model_number": _plain(), "part_number": _plain(),
    "purchasable_offer": _plain(), "fulfillment_availability": _plain(),
    "list_price": _plain({"value": {"type": "number"}, "currency": {"type": "string"}}),
    "main_product_image_locator": _plain({"media_location": {"type": "string"}}),
    **{"other_product_image_locator_%d" % i: _plain({"media_location": {"type": "string"}})
       for i in range(1, 9)},
    "externally_assigned_product_identifier": _plain({"type": {"type": "string"}}),
    "supplier_declared_has_product_identifier_exemption": _bool(),
    "merchant_shipping_group": _plain(),
    "country_of_origin": _enum(["GB", "CN", "US", "DE"]),
    "number_of_items": _num(), "unit_count": _num(),
    "item_dimensions": _dim(["length", "width", "height"]),
    "item_package_dimensions": _dim(["length", "width", "height"]),
    "item_weight": _weight(), "item_package_weight": _weight(),
    "website_shipping_weight": _weight(),
})
BATTERY = dict(BASIC, **{
    "batteries_required": _bool(), "batteries_included": _bool(),
    "contains_battery_or_cell": _bool(),
    "battery": {"type": "array", "items": {"type": "object", "properties": {
        "cell_composition": {"type": "array", "items": {"type": "object", "properties": {
            "value": {"type": "string", "enum": ["lithium_ion", "alkaline", "NiMH"]}}}},
        "iec_code": {"type": "array", "items": {"type": "object", "properties": {
            "value": {"type": "string"}}}},
        "weight": {"type": "array", "items": {"type": "object", "properties": {
            "value": {"type": "number"}, "unit": {"type": "string"}}}},
        "marketplace_id": {"type": "string"}}}},
    "num_batteries": _plain({"quantity": {"type": "integer"}, "type": {"type": "string"}}),
    "battery_installation_device_type": _enum(["battery_designed_to_be_installed_in_device",
                                               "battery_packed_with_device", "battery_only"]),
    "lithium_battery": {"type": "array", "items": {"type": "object", "properties": {
        "energy_content": {"type": "array"}, "packaging": {"type": "array"},
        "weight": {"type": "array"}, "marketplace_id": {"type": "string"}}}},
    "number_of_lithium_ion_cells": _num(), "number_of_lithium_metal_cells": _num(),
    "supplier_declared_dg_hz_regulation": _enum(["not_applicable", "ghs", "transportation",
                                                 "storage", "other"]),
    "ghs": {"type": "array", "items": {"type": "object", "properties": {
        "classification": {"type": "array", "items": {"type": "object", "properties": {
            "class": {"type": "string", "enum": ["flammable", "explosive", "compressed_gas"]}}}},
        "marketplace_id": {"type": "string"}}}},
    "hazmat": {"type": "array", "items": {"type": "object", "properties": {
        "aspect": {"type": "string", "enum": ["united_nations_regulatory_id", "transportation_regulatory_class"]},
        "value": {"type": "string"}, "marketplace_id": {"type": "string"}}}},
    "safety_data_sheet_url": _plain(),
    "wattage": _plain({"value": {"type": "number"}, "unit": {"type": "string", "enum": ["watts"]}}),
    "power_source_type": _enum(["battery_powered", "corded_electric", "solar_powered"]),
    "light_source": _plain({"type": {"type": "string"}}),
})

BATTERY_FULL = dict(BATTERY, battery={"type": "array", "items": {"type": "object", "properties": {
    "cell_composition": {"type": "array", "items": {"type": "object", "properties": {
        "value": {"type": "string", "enum": ["lithium_ion", "lithium_polymer", "alkaline"]}}}},
    "average_life": {"type": "array"}, "weight": {"type": "array"},
    "charge_time": {"type": "array"}, "capacity": {"type": "array"},
    "marketplace_id": {"type": "string"}}}})

BASE_ROW = {
    "SKU": "12.99_2Days_B0GOLDEN01", "Product Type": "KITCHEN",
    "Title": "Stainless Steel Garlic Press with Silicone Peeler",
    "Bullet 1": "Crushes garlic in one squeeze", "Bullet 2": "Dishwasher safe",
    "Bullet 3": "Soft-grip handle", "Bullet 4": "", "Bullet 5": "Lifetime guarantee",
    "Description (HTML)": "<p>A <b>sturdy</b> press.</p>\n<p>Easy to clean.</p>",
    "Search Terms / KW": "garlic crusher mincer kitchen gadget",
    "Brand": "Jack Reacherd", "Model Number": "JR-GP-001",
    "Our Price (GBP)": "12.99", "Handling Days": "2", "UPC": "",
    "Colour": "Silver", "Material": "Stainless Steel", "Country of Origin": "CN",
}

CFG = {"_account_id": "jack_uk", "brands": ["Jack Reacherd"], "default_quantity": 7,
       "merchant_shipping_group": "legacy-template-id"}


def _row(**kw):
    r = dict(BASE_ROW)
    for k, v in kw.items():
        r[k.replace("__", " ")] = v
    return r


def _pa(d):
    return json.dumps(d)


# (name, row, product_type, props, required, config)
CASES = [
    ("kitchen_basic", _row(), "KITCHEN", BASIC, ["item_name", "brand"], CFG),
    ("no_schema", _row(), "KITCHEN", {}, [], CFG),
    ("real_barcode", _row(UPC="5060541510005"), "KITCHEN", BASIC, ["item_name"], CFG),
    ("exemption_ticked", _row(**{"GTIN Exemption": "yes"}), "KITCHEN", BASIC, ["item_name"], CFG),
    ("fake_barcode", _row(UPC="000000000000"), "KITCHEN", BASIC, ["item_name"], CFG),
    ("poisoned_asin", _row(**{"Attributes JSON": _pa({
        "merchant_suggested_asin": [{"value": "B0COMPETIT"}]})}), "KITCHEN", BASIC, ["item_name"], CFG),
    ("foreign_brand", _row(Brand="SomeoneElse"), "KITCHEN", BASIC, ["item_name", "brand"], CFG),
    ("images", _row(**{"Attributes JSON": _pa({
        "main_product_image_locator": "https://m.media-amazon.com/images/I/competitor.jpg",
        "other_product_image_locator_1": "https://example.com/own/1.jpg",
        "other_product_image_locator_2": "/media/SKU/local.png",
        "other_product_image_locator_3": "not a url"})}), "KITCHEN", BASIC, ["item_name"], CFG),
    ("dims_flat", _row(**{"Attributes JSON": _pa({
        "item_length": "20", "item_width": "5", "item_height": "4", "item_weight": "250",
        "item_package_length": "22", "item_package_width": "6", "item_package_height": "5",
        "item_package_weight": "300"})}), "KITCHEN", BASIC,
     ["item_name", "item_dimensions", "item_package_dimensions"], CFG),
    ("dims_nested_dotkeys", _row(**{"Attributes JSON": _pa({
        "item_dimensions.length.value": "20", "item_dimensions.length.unit": "centimeters",
        "item_dimensions.width.value": "5", "item_dimensions.width.unit": "centimeters",
        "item_dimensions.height.value": "4", "item_dimensions.height.unit": "centimeters",
        "leg": "feet", "leg.length.decimal_value": "50.0", "leg.length.unit": "feet"})}),
     "KITCHEN", BASIC, ["item_name"], CFG),
    ("pa_mapping_and_unknown", _row(**{"Attributes JSON": _pa({
        "special_feature": ["Rust resistant", "Ergonomic"], "warranty_description": "2 years",
        "fulfillment_quantity": "3", "made_up_field": "x", "_provenance": {"Title": "ai"},
        "provenance": {"x": 1}, "manufacturer": "Acme Ltd", "part_number": "P-9"})}),
     "KITCHEN", BASIC, ["item_name"], CFG),
    ("battery_lithium", _row(Title="Rechargeable LED Torch 1000 Lumens",
                             **{"Product Type": "FLASHLIGHT", "Batteries Included": "Yes",
                                "Attributes JSON": _pa({
                                    "battery": {"cell_composition": "lithium_ion", "weight": {"value": "45", "unit": "grams"}},
                                    "num_batteries": "1", "power_source_type": "battery_powered",
                                    "light_source": "LED", "wattage": "10W"})}),
     "FLASHLIGHT", BATTERY, ["item_name", "batteries_required", "supplier_declared_dg_hz_regulation"], CFG),
    ("battery_none", _row(Title="Wooden Spoon Set",
                          **{"Batteries Included": "No", "Attributes JSON": _pa({"power_source_type": "manual"})}),
     "KITCHEN", BATTERY, ["item_name", "batteries_required", "supplier_declared_dg_hz_regulation",
                          "contains_battery_or_cell"], CFG),
    ("massager_corded", _row(Title="Electric Neck Massager", **{"Product Type": "MASSAGER",
                             "Attributes JSON": _pa({"power_source_type": "corded_electric",
                                                     "wattage": "24", "ghs": "flammable"})}),
     "MASSAGER", BATTERY, ["item_name", "supplier_declared_dg_hz_regulation", "ghs"], CFG),
    ("uk_responsible_person", _row(), "KITCHEN", dict(BASIC, gpsr_safety_attestation=_bool(),
                                                      dsa_responsible_party_address=_plain()),
     ["item_name"], dict(CFG, _uk_responsible_person={"name": "RP Ltd", "address": "1 Road, London"})),
    ("required_backfill", _row(Title="", **{"Bullet 1": "", "Bullet 2": "", "Bullet 3": "",
                                             "Bullet 5": "", "Description (HTML)": ""}),
     "KITCHEN", BASIC, ["item_name", "bullet_point", "product_description", "number_of_items",
                        "unit_count", "country_of_origin", "item_type_keyword"], CFG),
    ("no_price_no_qty", _row(**{"Our Price (GBP)": "", "Handling Days": ""}), "KITCHEN", BASIC,
     ["item_name"], {k: v for k, v in CFG.items() if k != "default_quantity"}),
]

# Branch-driving schemas: composite dimensions, boolean / N/A snapping, and the
# Rule 1 field present in the schema (so its last-line drop is exercised).
COMPOSITE = dict(BASIC, **{
    "item_length_width": {"type": "array", "items": {"type": "object", "properties": {
        "length": {"type": "array", "items": {"type": "object", "properties": {
            "decimal_value": {"type": "number"}, "unit": {"type": "string", "enum": ["feet", "meters"]}}}},
        "width": {"type": "array", "items": {"type": "object", "properties": {
            "decimal_value": {"type": "number"}, "unit": {"type": "string", "enum": ["feet", "meters"]}}}},
        "marketplace_id": {"type": "string"}}}},
    "furniture_leg": {"type": "array", "items": {"type": "object", "properties": {
        "length": {"type": "object", "properties": {"value": {"type": "number"},
                                                    "unit": {"type": "string"}}},
        "color": {"type": "array", "items": {"type": "object", "properties": {"value": {"type": "string"}}}},
        "material": {"type": "array", "items": {"type": "object", "properties": {"value": {"type": "string"}}}},
        "marketplace_id": {"type": "string"}}}},
    "is_fragile": _enum(["true", "false"]),
    "item_shape": _enum(["Round", "Square", "Rectangular", "Oval"]),
    "material": _plain({"value": {"type": "string", "enum": ["Aluminium", "Plastic", "Stainless Steel", "Wood"]}}),
    "merchant_suggested_asin": _plain(),
})
CASES += [
    ("composite_dims", _row(**{"Attributes JSON": _pa({
        "item_length_width": {"length": {"decimal_value": "2.5", "unit": "feet"},
                              "width": [{"value": "1", "unit": "feet"}]},
        "furniture_leg": {"length": {"value": "30", "unit": "centimeters"},
                          "color": {"value": "Black"}, "material": [{"value": "Oak"}],
                          "height": ""},
        "item_length": "30", "item_width": "10"})}),
     "FURNITURE", COMPOSITE, ["item_name", "item_length_width"], CFG),
    ("snapping", _row(**{"Attributes JSON": _pa({
        "is_fragile": "No", "item_shape": "N/A", "material": "stainless steel",
        "merchant_suggested_asin": "B0COMPETIT"})}), "KITCHEN", COMPOSITE, ["item_name"], CFG),
    ("battery_flags_no", _row(Title="USB Rechargeable Fan", **{"Attributes JSON": _pa({
        "batteries_required": "No", "batteries_included": "no", "num_batteries": "0",
        "power_source_type": "corded_electric"})}),
     "FAN", BATTERY, ["item_name", "batteries_required", "contains_battery_or_cell",
                      "supplier_declared_dg_hz_regulation", "battery"], CFG),
    ("battery_detail", _row(Title="Lithium Rechargeable Torch", **{"Attributes JSON": _pa({
        "battery.cell_composition": "lithium_ion", "battery.iec_code": "18650",
        "battery.weight.value": "45", "battery.weight.unit": "grams",
        "battery.average_life.value": "8", "battery.average_life.unit": "hours",
        "battery.charge_time.value": "3", "battery.charge_time.unit": "hours",
        "battery.capacity.value": "2600", "battery.capacity.unit": "milliamp_hours",
        "num_batteries": "2", "batteries_required": "yes", "batteries_included": "yes",
        "lithium_battery.energy_content": "9.6", "number_of_lithium_ion_cells": "2",
        "ghs": "", "hazmat": "UN3481", "safety_data_sheet_url": "https://example.com/sds.pdf",
        "wattage": "0", "supplier_declared_dg_hz_regulation": "ghs"})}),
     "FLASHLIGHT", BATTERY, ["item_name", "battery", "num_batteries", "batteries_required",
                             "batteries_included", "supplier_declared_dg_hz_regulation",
                             "ghs", "lithium_battery", "wattage"], CFG),
    ("battery_subfields", _row(Title="USB Rechargeable Neck Massager", **{"Attributes JSON": _pa({
        "battery.cell_composition": [{"value": "lithium_polymer"}],
        "battery.average_life": [{"value": "5", "unit": "hours"}],
        "battery.charge_time.value": "2", "battery.charge_time.unit": "hours",
        "battery.capacity": {"value": "1800", "unit": "milliamp_hour"},
        "num_batteries": "1", "power_source_type": "battery_powered"})}),
     "MASSAGER", BATTERY_FULL, ["item_name", "battery", "num_batteries", "power_source_type"], CFG),
    ("backfill_battery_no_evidence", _row(Title="Mechanical Timer lasts 12 hours",
                                          **{"Attributes JSON": _pa({"num_batteries": "aa"})}),
     "KITCHEN", dict(BASIC, battery=_plain(), num_batteries=BATTERY["num_batteries"],
                     light_source=BATTERY["light_source"], wattage=BATTERY["wattage"],
                     safety_data_sheet_url=_plain(), included_in_warranty=_loc(), style=_loc(),
                     is_assembly_required=_bool(),
                     supplier_declared_dg_hz_regulation=BATTERY["supplier_declared_dg_hz_regulation"]),
     ["item_name", "battery", "num_batteries", "light_source", "wattage", "safety_data_sheet_url",
      "included_in_warranty", "style", "is_assembly_required", "supplier_declared_dg_hz_regulation"], CFG),
    ("ghs_regulation_without_class", _row(Title="Lighter Refill Gas", **{"Attributes JSON": _pa({
        "supplier_declared_dg_hz_regulation": "ghs"})}),
     "HOUSEHOLD", dict(BASIC, supplier_declared_dg_hz_regulation=BATTERY["supplier_declared_dg_hz_regulation"]),
     ["item_name", "supplier_declared_dg_hz_regulation"], CFG),
    ("battery_alkaline", _row(Title="Kitchen Timer with AAA Battery", **{"Attributes JSON": _pa({
        "battery": {"cell_composition": "alkaline"}, "num_batteries": "1",
        "wattage": "about 3 watts"})}),
     "KITCHEN", BATTERY, ["item_name", "battery", "num_batteries", "batteries_required",
                          "contains_battery_or_cell", "battery_installation_device_type"],
     dict(CFG, battery_installation_device_type_default="battery_packed_with_device")),
]
