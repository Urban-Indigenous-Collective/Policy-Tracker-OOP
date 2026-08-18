# Federal Source Bootstrap Report

Generated: 2026-08-02

## USAO district coverage

- Canonical federal districts: **94** (93 office sites; Guam + NMI share `usao-gu`)
- Canonical office slugs loaded: **93**
- Main v3 USAO districts found: **3**
- Added from canonical template (not in Main v3): **90**

### Main v3 USAO seeds

- `usao-ak` — 4 ref(s), states=['AK'], example=https://www.justice.gov/usao-ak/pr/pilot-projects-launched-address-missing-and-murdered-indigenous-persons
- `usao-or` — 2 ref(s), states=['OR'], example=https://www.justice.gov/usao-or/page/file/1368976/download
- `usao-wdmi` — 1 ref(s), states=['MI'], example=https://www.justice.gov/usao-wdmi/pr/2020_1218_MMIP

### Districts added from canonical template

- `usao-az` — Arizona
- `usao-cdca` — California, Central
- `usao-cdil` — Illinois, Central
- `usao-co` — Colorado
- `usao-ct` — Connecticut
- `usao-dc` — District of Columbia
- `usao-de` — Delaware
- `usao-edar` — Arkansas, Eastern
- `usao-edca` — California, Eastern
- `usao-edky` — Kentucky, Eastern
- `usao-edla` — Louisiana, Eastern
- `usao-edmi` — Michigan, Eastern
- `usao-edmo` — Missouri, Eastern
- `usao-ednc` — North Carolina, Eastern
- `usao-edny` — New York, Eastern
- `usao-edok` — Oklahoma, Eastern
- `usao-edpa` — Pennsylvania, Eastern
- `usao-edtn` — Tennessee, Eastern
- `usao-edtx` — Texas, Eastern
- `usao-edva` — Virginia, Eastern
- `usao-edwa` — Washington, Eastern
- `usao-edwi` — Wisconsin, Eastern
- `usao-gu` — Guam & N. Mariana Islands
- `usao-hi` — Hawaii
- `usao-id` — Idaho
- `usao-ks` — Kansas
- `usao-ma` — Massachusetts
- `usao-md` — Maryland
- `usao-mdal` — Alabama, Middle
- `usao-mdfl` — Florida, Middle
- `usao-mdga` — Georgia, Middle
- `usao-mdla` — Louisiana, Middle
- `usao-mdnc` — North Carolina, Middle
- `usao-mdpa` — Pennsylvania, Middle
- `usao-mdtn` — Tennessee, Middle
- `usao-me` — Maine
- `usao-mn` — Minnesota
- `usao-mt` — Montana
- `usao-nd` — North Dakota
- `usao-ndal` — Alabama, Northern
- `usao-ndca` — California, Northern
- `usao-ndfl` — Florida, Northern
- `usao-ndga` — Georgia, Northern
- `usao-ndia` — Iowa, Northern
- `usao-ndil` — Illinois, Northern
- `usao-ndin` — Indiana, Northern
- `usao-ndms` — Mississippi, Northern
- `usao-ndny` — New York, Northern
- `usao-ndoh` — Ohio, Northern
- `usao-ndok` — Oklahoma, Northern
- `usao-ndtx` — Texas, Northern
- `usao-ndwv` — West Virginia, Northern
- `usao-ne` — Nebraska
- `usao-nh` — New Hampshire
- `usao-nj` — New Jersey
- `usao-nm` — New Mexico
- `usao-nv` — Nevada
- `usao-pr` — Puerto Rico
- `usao-ri` — Rhode Island
- `usao-sc` — South Carolina
- `usao-sd` — South Dakota
- `usao-sdal` — Alabama, Southern
- `usao-sdca` — California, Southern
- `usao-sdfl` — Florida, Southern
- `usao-sdga` — Georgia, Southern
- `usao-sdia` — Iowa, Southern
- `usao-sdil` — Illinois, Southern
- `usao-sdin` — Indiana, Southern
- `usao-sdms` — Mississippi, Southern
- `usao-sdny` — New York, Southern
- `usao-sdoh` — Ohio, Southern
- `usao-sdtx` — Texas, Southern
- `usao-sdwv` — West Virginia, Southern
- `usao-ut` — Utah
- `usao-vi` — Virgin Islands
- `usao-vt` — Vermont
- `usao-wdar` — Arkansas, Western
- `usao-wdky` — Kentucky, Western
- `usao-wdla` — Louisiana, Western
- `usao-wdmo` — Missouri, Western
- `usao-wdnc` — North Carolina, Western
- `usao-wdny` — New York, Western
- `usao-wdok` — Oklahoma, Western
- `usao-wdpa` — Pennsylvania, Western
- `usao-wdtn` — Tennessee, Western
- `usao-wdtx` — Texas, Western
- `usao-wdva` — Virginia, Western
- `usao-wdwa` — Washington, Western
- `usao-wdwi` — Wisconsin, Western
- `usao-wy` — Wyoming

## Next steps

1. Review `sources/federal_sources.json` USAO rows
2. Set `review_needed: false` on verified listing URLs
3. Wire `FederalSiteSource` in discovery pipeline
4. Run federal discovery dry-run against known Main v3 DOJ MMIP examples
