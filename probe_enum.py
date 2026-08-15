# Print the EXACT schema structure + enum values for the 3 failing FLASHLIGHT
# fields, so we stop guessing. Run on Windows:  py -3.11 test_enum.py
import json, urllib.request, urllib.parse

c = json.load(open('config.json', encoding='utf-8'))
a = [x for x in c['accounts'] if x.get('id') == 'sheelady_us'][0]
cid, csec, rt = a['lwa_client_id'], a['lwa_client_secret'], a['refresh_token']
mid = 'ATVPDKIKX0DER'
ep  = 'https://sellingpartnerapi-na.amazon.com'

# 1) access token
body = urllib.parse.urlencode({'grant_type': 'refresh_token', 'refresh_token': rt,
                               'client_id': cid, 'client_secret': csec}).encode()
req = urllib.request.Request('https://api.amazon.com/auth/o2/token', data=body,
                             headers={'Content-Type': 'application/x-www-form-urlencoded'})
tok = json.loads(urllib.request.urlopen(req, timeout=30).read())['access_token']
print('token OK\n')

def get_schema(enforced):
    q = {'marketplaceIds': mid, 'requirements': 'LISTING', 'locale': 'en_US'}
    if enforced:
        q['requirementsEnforced'] = 'ENFORCED'
    url = f'{ep}/definitions/2020-09-01/productTypes/FLASHLIGHT?' + urllib.parse.urlencode(q)
    r = urllib.request.Request(url, headers={'x-amz-access-token': tok})
    meta = json.loads(urllib.request.urlopen(r, timeout=30).read())
    link = meta.get('schema', {}).get('link', {}).get('resource', '')
    sreq = urllib.request.Request(link, headers={'Accept': 'application/json'})
    return json.loads(urllib.request.urlopen(sreq, timeout=60).read())

for label, enf in [('ENFORCED', True), ('UNENFORCED (full defs)', False)]:
    print('=' * 60)
    print(label)
    print('=' * 60)
    s = get_schema(enf)
    props = s.get('properties', {})
    print('required:', s.get('required', []))
    for f in ['battery', 'num_batteries', 'light_source']:
        p = props.get(f)
        if not p:
            print(f'\n{f}: NOT in properties')
        else:
            print(f'\n{f} FULL DEF:')
            print(json.dumps(p, indent=2)[:1500])
    print()
