// ===================== BRINGING LISTINGS IN FROM THE SHEET =====================
//
// "can you please explain why are we hitting the sheet problem again and again,
//  we made an app independent of the sheets"
//
// Because only half of that was ever done. The CODE moved off Sheets -- the
// generator writes to the app's own store, and so does everything else. The
// DATA did not: the accounts still have their spreadsheets configured, and on
// the server that spreadsheet is where the history actually is. The one-time
// import existed all along, but only as a command line run against a local
// database, so it was run on a laptop and never on the machine that serves the
// app.
//
// This is that import, reachable from the screen where the problem shows.
//
// ALWAYS TWO STEPS. The check reports exactly what a real run would do and
// writes nothing. Only then is there something to confirm -- a button that
// silently writes several hundred rows on first click is one nobody can safely
// press to find out what it does.
//
// The sheet is never written to, in either step.

async function migrateCheck(){
  const id = (typeof CUR_ACCOUNT !== "undefined" && CUR_ACCOUNT)
             ? String(CUR_ACCOUNT.id || "") : "";
  if(!id){ toast("Open an account first."); return; }
  toast("Reading the sheet…");
  let j;
  try{
    j = await (await fetch("/migrate/import", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({id:id, dry_run:true})})).json();
  }catch(e){ toast("Could not read the sheet: " + e); return; }
  if(!j || !j.ok){ toast((j && j.error) || "Could not read the sheet"); return; }

  const lines = [
    j.sheet_rows + " row(s) in the spreadsheet",
    j.imported + " would be brought into the app",
    j.skipped + " skipped (no SKU, so nothing to identify them by)",
    "the app currently holds " + j.before,
  ];
  // Columns the mapping does not know are the one thing that loses information
  // quietly, so they are named rather than counted.
  if((j.unknown_headers || []).length){
    lines.push("");
    lines.push("These columns are not understood and their data would NOT be "
               + "brought in:");
    lines.push("   " + j.unknown_headers.join(", "));
  }
  lines.push("");
  lines.push("The spreadsheet is only read. Nothing is written to it.");
  lines.push("");
  lines.push("Bring them in now?");

  if(!await uiConfirm(lines.join("\n"))) return;

  toast("Bringing them in…");
  let r;
  try{
    r = await (await fetch("/migrate/import", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({id:id, dry_run:false})})).json();
  }catch(e){ toast("Import failed: " + e); return; }
  if(!r || !r.ok){ toast((r && r.error) || "Import failed"); return; }

  const errs = (r.errors || []).length;
  toast(r.imported + " listing(s) brought in — the app now holds " + r.after
        + (errs ? ("; " + errs + " row(s) had problems") : ""));
  if(errs){
    console.log("Rows that could not be imported:", r.errors);
  }
  // Reload so the screen shows them from the app's own store, and the notice
  // above goes away on its own.
  if(typeof loadRows === "function") loadRows();
}
