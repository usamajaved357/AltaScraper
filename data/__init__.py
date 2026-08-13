"""data/ -- the SQLite backend for the beta.

PLAIN ENGLISH
The app currently keeps every listing in a Google Sheet. That works, but a sheet
is slow to read, rate-limited by Google, and can only be written a few rows at a
time. This package is the replacement: a real database file that lives on the
server, reads instantly and has no quota.

It is deliberately a SEPARATE backend. Nothing here touches the Google Sheets
code, and the existing app keeps running on sheets exactly as before. The two can
run side by side on different ports.

  db.py            the database file, its tables, and how to connect
  column_map.py    translates between the sheet's column names and the DB's
  store.py         ListingStore -- what the rest of the app talks to
  import_sheets.py one-time copy of an existing sheet into the database
  scheduler.py     background jobs (catalogue sync, ASIN monitor, inventory)

THE ONE IDEA THAT MAKES THIS WORK
ListingStore.get_all_rows() returns dictionaries keyed by the SHEET's column
names ("Buy Box Price (GBP)", not "buy_box_price"). That is the same shape the
sheet reader already returns, so the ~300 places in the app that read a row keep
working untouched. The translation happens here, once, instead of in 300 call
sites.
"""
