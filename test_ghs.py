# Dumps Amazon's EXACT structure + allowed values for the `ghs` field on
# FLASHLIGHT (US), so we know precisely what to send.
# Run on Windows in the app folder:  py -3.11 test_ghs.py
import json, urllib.request, urllib.parse

c = json.load(open('config.json', encoding='utf-8'))
a = [x for x in c['accounts'] if x.get('id') == 'sheelady_us'][0]
cid, csec, rt = a['lwa_client_id'], a['lwa_client_secret'], a['refresh_token']
mid = 'ATVPDKIKX0DER'                 # US
ep  = 'https://sellingpartnerapi-na.amazon.com'
PT  = 'FLASHLIGHT'

body = urllib.parse.urlencode({'grant_type': 'refresh_token', 'refresh_token': rt,
                               'client_id': cid, 'client_secret': csec}).encode()
req = urllib.request.Request('https://api.amazon.com/auth/o2/token', data=body,
                             headers={'Content-Type': 'application/x-www-form-urlencoded'})
tok = json.loads(urllib.request.urlopen(req, timeout=30).read())['access_token']
print('token OK\n')

def get_schema():
    q = {'marketplaceIds': mid, 'requirements': 'LISTING', 'locale': 'en_US'}
    url = f'{ep}/definitions/2020-09-01/productTypes/{PT}?' + urllib.parse.urlencode(q)
    r = urllib.request.Request(url, headers={'x-amz-access-token': tok})
    meta = json.loads(urllib.request.urlopen(r, timeout=30).read())
    link = meta.get('schema', {}).get('link', {}).get('resource', '')
    sreq = urllib.request.Request(link, headers={'Accept': 'application/json'})
    return json.loads(urllib.request.urlopen(sreq, timeout=60).read())

s = get_schema()
props = s.get('properties', {})
required = s.get('required', [])

print('=== is ghs REQUIRED? ===')
print('  ghs in required list:', 'ghs' in required)
print()

print('=== FULL ghs schema definition ===')
ghs = props.get('ghs', {})
print(json.dumps(ghs, indent=2)[:4000])
print()

# walk into the structure and list every enum we find
print('=== every allowed-value list found under ghs ===')
def walk(node, path='ghs'):
    if isinstance(node, dict):
        if isinstance(node.get('enum'), list):
            print(f'  {path}.enum = {node["enum"]}')
        for k, v in node.items():
            if k in ('properties', 'items'):
                walk(v, path + '.' + k)
            elif isinstance(v, (dict, list)):
                walk(v, path + '.' + k)
    elif isinstance(node, list):
        for i, it in enumerate(node):
            walk(it, f'{path}[{i}]')
walk(ghs)

print()
print('=== what the app will now build (preview) ===')
# mirror _build_ghs_from_schema quickly
items = ghs.get('items', {}) if isinstance(ghs.get('items'), dict) else {}
item_props = items.get('properties', {}) or ghs.get('properties', {})
print('  ghs item sub-fields:', list(item_props.keys()) if isinstance(item_props, dict) else '(none)')
