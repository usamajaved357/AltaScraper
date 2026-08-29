// ===================== BRINGING LISTINGS IN FROM THE SHEET =====================
//
// NOTHING TO PRESS HERE ANY MORE. This file used to hold migrateCheck(): a
// two-step flow behind a notice on the listings screen, which read the
// spreadsheet, reported what would be copied, and asked before copying it.
//
//     "Bring in whatever is left automatically right now, then remove this
//      banner entirely. It should never appear again. ... We are fully on the
//      database now."
//
// The check-then-confirm shape was right while this was a decision. It stopped
// being one. The listings read now brings in anything still only in the
// spreadsheet as it finds it -- see the auto-import in /rows_all
// (routes/listing_routes.py) and domain/sheet_migration.py, which is where the
// copy and the tab rule actually live.
//
// The safety that mattered did not move: the spreadsheet is only ever READ,
// never written to, so the original stays as the fallback; and rows are
// upserted by SKU, so importing twice overwrites rather than duplicates.
//
// /migrate/import is still there and still defaults to a dry run. It is now
// reached from routes/migrate_routes.py for a deliberate one-account import,
// not from this screen.
//
// Kept as a file rather than deleted because templates/dashboard.html loads it
// by name; an empty file is a smaller change than a template edit, and this
// note is the thing a reader looking for the old button needs to find.
