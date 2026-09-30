"""domain/currency.py -- a currency code (or a marketplace) -> the symbol to print.

The server-side twin of static/js/money.js (CUR_SYMBOLS / curSymbol), kept to
the same map so a notification and the screen print the same symbol. Made for
the repricer's price-move notification, which printed "$" for the US and "£"
for everything else -- so a price move on Amazon.de read as pounds (repricer
bug hunt, 30 Sep 2026).

AN UNKNOWN CODE RETURNS THE CODE, not a guessed symbol, as money.js does.
Which currency a marketplace sells in is domain/sourcing.CURRENCY_FOR, the one
table for that (Rule 12).
"""

SYMBOLS = {
    "GBP": "£", "USD": "$", "EUR": "€", "JPY": "¥",
    "CAD": "C$", "AUD": "A$", "SGD": "S$", "NZD": "NZ$",
    "SEK": "kr", "PLN": "zł", "AED": "AED ", "INR": "₹",
    "MXN": "MX$", "BRL": "R$", "TRY": "₺", "SAR": "SAR ", "EGP": "EGP ",
    "CHF": "CHF ", "NOK": "kr", "DKK": "kr", "CZK": "Kč", "HUF": "Ft",
}


def symbol(code, fallback=""):
    """The symbol for a currency CODE; the code itself when it is not known;
    `fallback` only when no code was given at all."""
    c = str(code or "").strip().upper()
    if not c:
        return fallback
    return SYMBOLS.get(c, c + " ")


def symbol_for_marketplace(marketplace, fallback="£"):
    """The symbol a marketplace's prices are in: "UK" -> £, "US" -> $, "DE" -> €."""
    from domain.sourcing import CURRENCY_FOR
    return symbol(CURRENCY_FOR.get(str(marketplace or "").strip().upper()), fallback)
