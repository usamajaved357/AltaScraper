# FULL dump of battery + ghs sub-properties (no truncation) so we can match the
# exact structure. Run on Windows in the app folder:  py -3.11 test_enum2.py
import json, urllib.request, urllib.parse

c = json.load(open('config.json', encoding='utf-8'))
a = [x for x in c['accounts'] if x.get('id') == 'sheelady_us'][0]
cid, csec, rt = a['lwa_client_id'], a['lwa_client_secret'], a['refresh_token']
mid = 'ATVPDKIKX0DER'
ep  = 'https://sellingpartnerapi-na.amazon.com'

body = urllib.parse.urlencode({'grant_type': 'refresh_token', 'refresh_token': rt,
                               'client_id': cid, 'client_secret': csec}).encode()
req = urllib.request.Request('https://api.amazon.com/auth/o2/token', data=body,
                             headers={'Content-Type': 'application/x-www-form-urlencoded'})
tok = json.loads(urllib.request.urlopen(req, timeout=30).read())['access_token']
print('token OK\n')

q = {'marketplaceIds': mid, 'requirements': 'LISTING', 'locale': 'en_US'}
url = f'{ep}/definitions/2020-09-01/productTypes/FLASHLIGHT?' + urllib.parse.urlencode(q)
r = urllib.request.Request(url, headers={'x-amz-access-token': tok})
meta = json.loads(urllib.request.urlopen(r, timeout=30).read())
link = meta.get('schema', {}).get('link', {}).get('resource', '')
sreq = urllib.request.Request(link, headers={'Accept': 'application/json'})
schema = json.loads(urllib.request.urlopen(sreq, timeout=60).read())
props = schema.get('properties', {})

def walk(name):
    p = props.get(name)
    if not p:
        print(f'{name}: NOT FOUND'); return
    print(f'\n========== {name} ==========')
    # list the sub-properties under items
    items = p.get('items', {})
    subprops = items.get('properties', {})
    req = items.get('required', [])
    print(f'items.required = {req}')
    print(f'sub-properties: {list(subprops.keys())}')
    for sub, sp in subprops.items():
        # for each sub-prop, show its type and any enum (drill one more level)
        st = sp.get('type', '?')
        line = f'  - {sub} (type={st})'
        # enum directly?
        if 'enum' in sp:
            line += f"  enum={sp['enum'][:12]}"
        # nested array -> items.properties.value.enum
        si = sp.get('items', {})
        sip = si.get('properties', {}) if isinstance(si, dict) else {}
        if 'value' in sip:
            vv = sip['value']
            line += f"  value.type={vv.get('type','?')}"
            # value may have anyOf with enum, or direct enum
            if 'enum' in vv:
                line += f"  value.enum={vv['enum'][:20]}"
            for ao in vv.get('anyOf', []):
                if 'enum' in ao:
                    line += f"  value.anyOf.enum={ao['enum'][:30]}"
        sreq2 = si.get('required', []) if isinstance(si, dict) else []
        if sreq2:
            line += f"  (sub-required={sreq2})"
        print(line)

for f in ['battery', 'ghs', 'special_feature', 'warranty_description', 'safety_data_sheet_url']:
    walk(f)
