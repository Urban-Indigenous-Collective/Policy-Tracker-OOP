# State Source Gap-Fill Report

Generated: 2026-08-01

## Summary

- States processed: 10
- Sources added: 23
- Candidates rejected by probe: 8

## Added sources

### IA

- `executive_order` IA — Governor executive orders
  - https://governor.iowa.gov/newsroom?category=executive-orders
  - probe: HTTP 200, 155607 bytes
- `proclamation` IA — Governor proclamations
  - https://governor.iowa.gov/newsroom?category=proclamations
  - probe: HTTP 200, 155573 bytes
- `legislature_search` IA — Legislature bill search (both chambers)
  - https://www.legis.iowa.gov/search?q={query}
  - probe: HTTP 200, 11330 bytes

### LA

- `executive_order` LA — Governor executive orders
  - https://gov.louisiana.gov/index.cfm?md=newsroom&tmp=archive&cat=Executive%20Orders
  - probe: HTTP 200, 219424 bytes
- `proclamation` LA — Governor proclamations
  - https://gov.louisiana.gov/index.cfm?md=newsroom&tmp=archive&cat=Proclamations
  - probe: HTTP 200, 219424 bytes
- `legislature_search` LA — Legislature bill search (both chambers)
  - https://www.legis.la.gov/legis/Law.aspx?d={query}
  - probe: HTTP 200, 19132 bytes

### ME

- `executive_order` ME — Governor executive orders
  - https://www.maine.gov/governor/mills/newsroom?category=executive-orders
  - probe: HTTP 200, 52272 bytes
- `proclamation` ME — Governor proclamations
  - https://www.maine.gov/governor/mills/official_documents/proclamations
  - probe: HTTP 200, 29421 bytes

### MS

- `executive_order` MS — Governor executive orders
  - https://governorreeves.ms.gov/category/executive-orders
  - probe: HTTP 200, 109995 bytes
- `proclamation` MS — Governor proclamations
  - https://governorreeves.ms.gov/category/proclamations
  - probe: HTTP 200, 109995 bytes

### MT

- `proclamation` MT — Governor proclamations
  - https://governor.mt.gov/newsroom/proclamations
  - probe: HTTP 200, 50808 bytes
- `legislature_search` MT — Legislature bill search (both chambers)
  - https://bills.legmt.gov/#/laws/bills?search={query}
  - probe: HTTP 200, 6042 bytes

### NE

- `executive_order` NE — Governor executive orders
  - https://governor.nebraska.gov/news?category=executive-orders
  - probe: HTTP 200, 29003 bytes
- `proclamation` NE — Governor proclamations
  - https://governor.nebraska.gov/news?category=proclamations
  - probe: HTTP 200, 29000 bytes
- `legislature_search` NE — Legislature bill search
  - https://nebraskalegislature.gov/bills/search_by_keyword.php?Keyword={query}
  - probe: HTTP 200, 19319 bytes

### RI

- `proclamation` RI — Governor proclamations
  - https://governor.ri.gov/press-releases?category=proclamations
  - probe: HTTP 200, 274513 bytes

### SC

- `executive_order` SC — Governor executive orders
  - https://governor.sc.gov/news?category=executive-orders
  - probe: HTTP 200, 112684 bytes
- `proclamation` SC — Governor proclamations
  - https://governor.sc.gov/news?category=proclamations
  - probe: HTTP 200, 112681 bytes
- `legislature_search` SC — Legislature bill search (both chambers)
  - https://www.scstatehouse.gov/billsearch.php?searchtext={query}
  - probe: HTTP 200, 26472 bytes

### TX

- `proclamation` TX — Governor proclamations
  - https://gov.texas.gov/news/category/proclamation
  - probe: HTTP 200, 95839 bytes
- `legislature_search` TX — Legislature bill search (both chambers)
  - https://capitol.texas.gov/Search/BillSearchResults.aspx?NSP=1&SPL=True&SPC=False&SPA=False&SPS=False&Leg=89&Sess=R&ChamberH=True&ChamberS=True&Search={query}
  - probe: HTTP 200, 60104 bytes

### VA

- `proclamation` VA — Governor proclamations
  - https://www.governor.virginia.gov/newsroom/proclamations
  - probe: HTTP 200, 63273 bytes
- `legislature_search` VA — Legislature bill search (both chambers)
  - https://lis.virginia.gov/cgi-bin/legp604.exe?251+men+BIL&q={query}
  - probe: HTTP 200, 9162 bytes

## Rejected candidates

- **ME** `agency_press` https://www.maine.gov/tribal-state/ — HTTP 404
- **ME** `legislature_search` https://legislature.maine.gov/search?q={query} — HTTP 404
- **MS** `legislature_search` http://billstatus.ls.state.ms.us/sessions.htm?q={query} — ssl error (HTTPSConnectionPool(host='billstatus.ls.state.ms.us', port=4)
- **MS** `legislature_session` http://billstatus.ls.state.ms.us/ — ssl error (HTTPSConnectionPool(host='billstatus.ls.state.ms.us', port=4)
- **MT** `legislature_session` https://leg.mt.gov/bills/ — HTTP 403
- **RI** `legislature_search` https://webserver.rilegislature.gov/Search/?q={query} — body too small (610 bytes)
- **RI** `legislature_session` https://www.rilegislature.gov/Pages/Bills.aspx — HTTP 404
- **TX** `executive_order` https://gov.texas.gov/news/category/executive-orders — ReadTimeout: HTTPSConnectionPool(host='gov.texas.gov', port=443): Read ti

