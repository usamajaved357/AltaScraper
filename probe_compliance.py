# Dumps Amazon's allowed values for ALL the safety/compliance fields on a product
# type, so we can confirm each one has a safe "not applicable" option.
# Run on Windows in the app folder:  py -3.11 test_compliance.py
# (defaults to FLASHLIGHT/US; pass a product type to change:  py -3.11 test_compliance.py LUGGAGE)
import json, sys, urllib.request, urllib.parse

PT  = sys.argv[1] if len(sys.argv) > 1 else 'FLASHLIGHT'
c = json.load(open('config.json', encoding='utf-8'))
a = [x for x in c['accounts'] if x.get('id') == 'sheelady_us'][0]
cid, csec, rt = a['lwa_client_id'], a['lwa_client_secret'], a['refresh_token']
mid = 'ATVPDKIKX0DER'                 # US
ep  = 'https://sellingpartnerapi-na.amazon.com'

body = urllib.parse.urlencode({'grant_type': 'refresh_token', 'refresh_token': rt,
                               'client_id': cid, 'client_secret': csec}).encode()
req = urllib.request.Request('https://api.amazon.com/auth/o2/token', data=body,
                             headers={'Content-Type': 'application/x-www-form-urlencoded'})
tok = json.loads(urllib.request.urlopen(req, timeout=30).read())['access_token']
print('token OK\n')

q = {'marketplaceIds': mid, 'requirements': 'LISTING', 'locale': 'en_US'}
url = f'{ep}/definitions/2020-09-01/productTypes/{PT}?' + urllib.parse.urlencode(q)
r = urllib.request.Request(url, headers={'x-amz-access-token': tok})
meta = json.loads(urllib.request.urlopen(r, timeout=30).read())
link = meta.get('schema', {}).get('link', {}).get('resource', '')
s = json.loads(urllib.request.urlopen(urllib.request.Request(link, headers={'Accept': 'application/json'}), timeout=60).read())

props = s.get('properties', {})
required = s.get('required', [])

FIELDS = ['hazmat', 'supplier_declared_dg_hz_regulation', 'ghs',
          'pesticide_marking', 'supplier_declared_material_regulation',
          'california_proposition_65_compliance_type', 'contains_liquid_contents',
          'batteries_required', 'batteries_included', 'battery',
          'num_batteries', 'number_of_lithium_ion_cells', 'lithium_battery',
          'battery_installation_device_type', 'power_source_type']

print(f'=== compliance fields for {PT} (US) ===')
print(f'required list has {len(required)} fields\n')

def find_enum(node, depth=0):
    """Recursively find the first enum list under a property node."""
    if isinstance(node, dict):
        if isinstance(node.get('enum'), list):
            return node['enum']
        for k in ('items', 'properties'):
            if k in node:
                r = find_enum(node[k], depth+1)
                if r: return r
        for v in node.values():
            if isinstance(v, dict):
                r = find_enum(v, depth+1)
                if r: return r
    return None

for f in FIELDS:
    in_req = f in required
    if f not in props:
        print(f'  {f:42} -> NOT in schema   {"(REQUIRED!)" if in_req else ""}')
        continue
    enum = find_enum(props[f])
    tag = '(REQUIRED)' if in_req else ''
    if enum:
        # flag whether a not-applicable-style option exists
        low = [str(e).lower() for e in enum]
        has_na = any(s in ' '.join(low) for s in ('not_applic', 'none', 'no_warning', 'not_regul', 'not_class'))
        print(f'  {f:42} {tag}')
        print(f'      values: {enum}')
        print(f'      has a not-applicable option: {has_na}')
    else:
        print(f'  {f:42} {tag} -> free text / nested (no simple enum)')
print('\nDone. Paste this whole output back.')
