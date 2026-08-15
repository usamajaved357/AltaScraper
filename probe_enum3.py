# Full structure for the lithium-battery group + ghs + battery.weight.
# Run on Windows in the app folder:  py -3.11 test_enum3.py
import json, urllib.request, urllib.parse

c = json.load(open('config.json', encoding='utf-8'))
a = [x for x in c['accounts'] if x.get('id') == 'sheelady_us'][0]
cid, csec, rt = a['lwa_client_id'], a['lwa_client_secret'], a['refresh_token']
mid = 'ATVPDKIKX0DER'; ep = 'https://sellingpartnerapi-na.amazon.com'

body = urllib.parse.urlencode({'grant_type':'refresh_token','refresh_token':rt,
                               'client_id':cid,'client_secret':csec}).encode()
req = urllib.request.Request('https://api.amazon.com/auth/o2/token', data=body,
                             headers={'Content-Type':'application/x-www-form-urlencoded'})
tok = json.loads(urllib.request.urlopen(req, timeout=30).read())['access_token']
print('token OK\n')

q = {'marketplaceIds': mid, 'requirements':'LISTING', 'locale':'en_US'}
url = f'{ep}/definitions/2020-09-01/productTypes/FLASHLIGHT?' + urllib.parse.urlencode(q)
r = urllib.request.Request(url, headers={'x-amz-access-token': tok})
meta = json.loads(urllib.request.urlopen(r, timeout=30).read())
link = meta.get('schema',{}).get('link',{}).get('resource','')
schema = json.loads(urllib.request.urlopen(urllib.request.Request(link, headers={'Accept':'application/json'}), timeout=60).read())
props = schema.get('properties', {})

def full(name):
    p = props.get(name)
    print(f'\n========== {name} ==========')
    if not p:
        print('  NOT in properties'); return
    items = p.get('items', {})
    sub = items.get('properties', {})
    print(f'items.required = {items.get("required", [])}')
    print(f'sub-properties: {list(sub.keys())}')
    for k, sp in sub.items():
        st = sp.get('type','?')
        info = f'  - {k} (type={st})'
        if 'enum' in sp: info += f"  enum={sp['enum']}"
        # nested
        si = sp.get('items', {})
        sip = si.get('properties', {}) if isinstance(si, dict) else {}
        if si: info += f"  items.required={si.get('required',[])}"
        for ck, cv in sip.items():
            ce = cv.get('enum')
            info += f"\n      .{ck} (type={cv.get('type','?')})" + (f" enum={ce[:25]}" if ce else "")
            for ao in cv.get('anyOf', []):
                if 'enum' in ao: info += f" anyOf.enum={ao['enum'][:25]}"
        print(info)

for f in ['lithium_battery','number_of_lithium_ion_cells','number_of_lithium_metal_cells',
          'contains_battery_or_cell','ghs','battery']:
    full(f)
