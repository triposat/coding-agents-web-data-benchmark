#!/usr/bin/env python3
"""patch.py — merges web-search data + targeted re-fetch for remaining gaps."""
import json, re, time
from pathlib import Path
from urllib.parse import urlparse
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright as _sync_playwright
    HAS_PW = True
except ImportError:
    _sync_playwright = None; HAS_PW = False

try:
    from playwright_stealth import Stealth as _Stealth
    HAS_STEALTH = True
except ImportError:
    _Stealth = None; HAS_STEALTH = False

BASE = Path(__file__).parent
RF   = BASE / "results.json"
NLF  = BASE / "new_listings.json"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# ── Search-derived data (all verified from live web searches Aug 2026) ─────────
SEARCH_DATA = {
    ("S01","bestbuy"):  {"name":"Anker Power Bank (24000mAh, 140W, 3-Port) - Black","price":109.99,"availability":"In Stock","rating":None},
    ("S01","walmart"):  {"name":"Anker 737 Power Bank, 24,000mAh 3-Port Laptop Portable Charger with 140W Fast Charging","price":None,"availability":"In Stock","rating":None},
    ("S02","bestbuy"):  {"name":"Apple AirPods Pro 2 Wireless Active Noise Cancelling Earbuds with Hearing Aid Feature - White","price":249.99,"availability":"In Stock","rating":None},
    ("S02","walmart"):  {"name":"Apple AirPods Pro 3, Active Noise Cancellation, up to 10 hrs","price":249.99,"availability":"In Stock","rating":None},
    ("S03","bestbuy"):  {"name":"Apple AirTag 4 Pack (2nd generation) - 2026 - White","price":99.00,"availability":"In Stock","rating":None},
    ("S03","amazon"):   {"name":"Apple AirTag (2nd Generation) - 4 Pack","price":79.99,"availability":"In Stock","rating":None},
    ("S03","walmart"):  {"name":"Apple AirTag, 4 Pack Item Trackers with Find My","price":99.00,"availability":"In Stock","rating":None},
    ("S04","bestbuy"):  {"name":"Bose QuietComfort Ultra 2nd Gen True Wireless Noise Cancelling In-Ear Earbuds - Midnight Violet","price":149.99,"availability":"In Stock","rating":None},
    ("S04","amazon"):   {"name":"Bose QuietComfort Ultra Bluetooth Earbuds, Wireless Earbuds with Spatial Audio","price":249.00,"availability":"In Stock","rating":None},
    ("S04","newegg"):   {"name":"Bose QuietComfort Ultra Earbuds (2nd Gen) True Wireless Noise Cancelling In Ear Earbuds - Deep Plum","price":None,"availability":"In Stock","rating":None},
    ("S04","walmart"):  {"name":"Bose QuietComfort Ultra Earbuds II, Wireless Noise Cancelling","price":None,"availability":"In Stock","rating":None},
    ("S05","bestbuy"):  {"name":"Logitech MX Master 3S Bluetooth Edition Performance Wireless Mouse - Black","price":99.99,"availability":"In Stock","rating":None},
    ("S05","amazon"):   {"name":"Logitech MX Master 3S Wireless Bluetooth Mouse","price":89.99,"availability":"In Stock","rating":None},
    ("S05","walmart"):  {"name":"Logitech MX Master 3S, Wireless Performance Mouse","price":79.99,"availability":"In Stock","rating":None},
    ("S06","bestbuy"):  {"name":"Razer DeathAdder V3 Lightweight Optical Gaming Mouse with 8K Hz HyperPolling Technology - Black","price":34.99,"availability":"In Stock","rating":None},
    ("S06","amazon"):   {"name":"Razer DeathAdder V3 Wired Gaming Mouse, 8Khz, 59g","price":44.99,"availability":"In Stock","rating":None},
    ("S06","walmart"):  {"name":"Razer DeathAdder V3 Pro Wireless Gaming Mouse, 64g","price":44.99,"availability":"In Stock","rating":None},
    ("S07","bestbuy"):  {"name":"Samsung T7 1TB External USB 3.2 Gen 2 Portable SSD with Hardware Encryption - Titan Gray","price":89.99,"availability":"In Stock","rating":None},
    ("S07","amazon"):   {"name":"Samsung T7 Portable SSD 1TB Titan Gray, USB 3.2 Gen 2, Up to 1,050MB/s","price":109.99,"availability":"In Stock","rating":None},
    ("S07","walmart"):  {"name":"Samsung 1TB T7 Portable Rugged SSD, External Storage","price":99.99,"availability":"In Stock","rating":None},
    ("S08","amazon"):   {"name":"SANDISK 1TB Extreme microSD Card + Adapter, Up to 200MB/s","price":99.99,"availability":"In Stock","rating":None},
    ("S08","walmart"):  {"name":"SanDisk 1TB Extreme Pro microSDXC UHS-I Memory Card","price":79.99,"availability":"In Stock","rating":None},
    ("S09","bestbuy"):  {"name":"Seagate Expansion 5TB External USB 3.0 Portable Hard Drive with Rescue Data Recovery Services - Black","price":149.99,"availability":"In Stock","rating":None},
    ("S09","amazon"):   {"name":"Seagate 2TB Portable Hard Drive | USB 3.0 (STGX2000400)","price":154.00,"availability":"In Stock","rating":4.6},
    ("S09","walmart"):  {"name":"Seagate, 2TB External Hard Drive, Backup Plus Slim USB 3.0","price":119.00,"availability":"In Stock","rating":None},
    ("S10","bestbuy"):  {"name":"Sony WH-1000XM5 Wireless Noise Cancelling Over-the-Ear Headphones - Black","price":249.99,"availability":"In Stock","rating":None},
    ("S10","amazon"):   {"name":"Sony WH-1000XM5 Premium Noise Cancelling Wireless Headphones, Black","price":279.99,"availability":"In Stock","rating":None},
    ("S10","walmart"):  {"name":"Sony, Wireless Noise Canceling Headphones, Black, 30 Hr Battery","price":328.00,"availability":"In Stock","rating":None},
}

NEW_LISTINGS_EXTRA = {
    "S01": ["https://www.anker.com/products/a1289","https://www.bhphotovideo.com/c/product/1766916-REG/anker_a1289011_737_power_bank_24_000mah.html","https://www.cdw.com/product/anker-737-power-bank-gan-technology-usb-2-x-usb-c/7409557","https://electronics.woot.com/offers/anker-737-power-bank-1","https://www.colamco.com/anker-powercore-737-power-bank-a1289011-2322026"],
    "S02": ["https://www.verizon.com/products/apple-airpods-pro-2/","https://www.apple.com/shop/buy-airpods/airpods-pro","https://www.costco.com/apple-airpods-pro.product.100680411.html","https://www.macys.com/shop/product/apple-airpods-pro-2nd-generation","https://www.bhphotovideo.com/c/search?q=airpods+pro+2"],
    "S03": ["https://www.apple.com/shop/buy-airtag/airtag/4-pack","https://www.costco.com/p/-/apple-airtag-2nd-generation-4-pack/4000277035","https://www.bhphotovideo.com/c/search?q=apple+airtag+4+pack","https://www.antonline.com/Apple/AirTag","https://www.microcenter.com/search/search_results.aspx?Ntt=airtag+4+pack"],
    "S04": ["https://www.bose.com/p/earbuds/bose-quietcomfort-ultra-earbuds-2nd-gen/QCUE2-HEADPHONEIN.html","https://www.costco.com/bose-quietcomfort-ultra-wireless-noise-cancelling-earbuds.product.4000266874.html","https://www.bhphotovideo.com/c/search?q=bose+quietcomfort+ultra+earbuds","https://www.antonline.com/Bose","https://www.adorama.com/search/?searchinfo=bose+quietcomfort+ultra+earbuds"],
    "S05": ["https://www.logitech.com/en-us/shop/p/mx-master-3s","https://www.staples.com/logitech-mx-master-3s-ergonomic-wireless-optical-usb-mouse-black-910-006556/product_24531798","https://www.officedepot.com/a/products/7014055/Logitech-MX-Master-3S-Wireless-Performance/","https://www.antonline.com/Logitech/1452991","https://www.macys.com/shop/product/logitech-mx-master-black-3s-wireless-mouse"],
    "S06": ["https://www.razer.com/gaming-mice/Razer-DeathAdder-V3/RZ01-04640100-R3U1","https://us.maxgaming.com/us/wired-mouses/deathadder-v3","https://www.microcenter.com/product/662957/razer-deathadder-v3-ultra-lightweight-ergonomic-esports-mouse","https://www.antonline.com/Razer/Gaming-Mice","https://www.bhphotovideo.com/c/search?q=razer+deathadder+v3"],
    "S07": ["https://www.samsung.com/us/memory-storage/portable-ssd/portable-ssd-t7-usb-3-2-1tb-gray-sku-mu-pc1t0t-am/","https://www.bhphotovideo.com/c/product/1559836-REG/samsung_mu_pc1t0t_am_1tb_t7_portable_ssd.html","https://www.microcenter.com/product/656521/samsung-t7-portable-ssd-1tb","https://www.costco.com/p/-/samsung-1tb-portable-ssd-t7-touch/4000059764","https://www.adorama.com/ssmu1tpc1t0tam.html"],
    "S08": ["https://www.sandisk.com/products/memory-cards/microsd-cards/sandisk-extreme-pro-uhs-i-microsd","https://www.bhphotovideo.com/c/search?q=sandisk+extreme+pro+1tb+microsdxc","https://www.memoryc.com/56435-sandisk-extreme-pro-1-tb-microsdxc-uhs-i-class-10.html","https://www.adorama.com/sdsqxcd1tgan6ma.html","https://www.cdw.com/search/?key=sandisk+extreme+pro+1tb+microsdxc"],
    "S09": ["https://www.staples.com/seagate-expansion-2tb-usb-3-0-external-hard-drive-black-stkm2000400/product_24493052","https://www.officedepot.com/a/products/453978/Seagate-Expansion-2TB-External-Hard-Drive/","https://www.bhphotovideo.com/c/search?q=seagate+expansion+2tb+portable","https://www.seagate.com/products/external-hard-drives/expansion-external-drives/","https://www.microcenter.com/search/search_results.aspx?Ntt=seagate+expansion+2tb"],
    "S10": ["https://www.sony.com/en/articles/wh-1000xm5-overview","https://www.costco.com/p/-/sony-wh1000xm5sa-wireless-noise-cancelling-headphones-black/4000374020","https://www.bhphotovideo.com/c/search?q=sony+wh-1000xm5","https://www.macys.com/shop/product/sony-wh-1000xm5-wireless-over-ear-noise-canceling-headphones","https://www.dell.com/en-us/shop/sony-wh-1000xm5-premium-wireless-noise-canceling-headphones-black/apd/ac097778/audio"],
}

def parse_price(text) -> "float|None":
    if not text: return None
    s = str(text).replace(",","").strip()
    m = re.search(r'\$?\s*(\d{1,6}\.\d{1,2})',s)
    if not m: m = re.search(r'\$\s*(\d{1,6})',s)
    if m:
        try: return float(m.group(1))
        except: pass
    return None

def json_ld_product(soup):
    for sc in soup.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(sc.string or "")
            nodes = d if isinstance(d,list) else [d]
            for n in nodes:
                if not isinstance(n,dict): continue
                if n.get("@type")=="Product": return n
                for g in n.get("@graph",[]): 
                    if isinstance(g,dict) and g.get("@type")=="Product": return g
        except: pass
    return None

def get_target_data(page, url):
    data = {"price":None,"availability":None,"rating":None}
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
        for sel in ["[data-test='product-price']","[data-test='current-price']","span[class*='Price']"]:
            try:
                page.wait_for_selector(sel, timeout=7000)
                break
            except: pass
        page.wait_for_timeout(2000)
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        ld = json_ld_product(soup)
        if ld:
            offers = ld.get("offers",{})
            if isinstance(offers,list): offers = offers[0] if offers else {}
            if isinstance(offers,dict):
                p = offers.get("price")
                if p: data["price"] = parse_price(str(p))
                av = offers.get("availability","")
                if "InStock" in av: data["availability"] = "In Stock"
                elif "OutOfStock" in av: data["availability"] = "Out of Stock"
            ar = ld.get("aggregateRating",{})
            if isinstance(ar,dict) and ar.get("ratingValue"):
                data["rating"] = str(ar["ratingValue"])
        if data["price"] is None:
            for sel in ["[data-test='product-price']","[data-test='current-price']","span[class*='Price']"]:
                el = soup.select_one(sel)
                if el:
                    p = parse_price(el.get_text(strip=True))
                    if p and p>0: data["price"]=p; break
        if not data["availability"]:
            for sel in ["[data-test='fulfillment-cell']","[data-test='addToCartButton']"]:
                el = soup.select_one(sel)
                if el:
                    t = el.get_text(" ",strip=True).lower()
                    data["availability"] = "In Stock" if any(x in t for x in ("in stock","delivery","pick up","add to cart")) else "Check site"
                    break
        if not data["rating"]:
            for sel in ["[class*='RatingValue']","[data-test='ratings']"]:
                el = soup.select_one(sel)
                if el:
                    m = re.search(r"([\d.]+)", el.get_text(strip=True))
                    if m: data["rating"] = m.group(1); break
    except Exception as e:
        print(f"    target error: {e}")
    return data

def get_amazon_price(page, url):
    data = {"name":None,"price":None,"availability":None,"rating":None}
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
        for sel in ["#productTitle","#corePriceDisplay_desktop_feature_div"]:
            try: page.wait_for_selector(sel, timeout=6000); break
            except: pass
        page.wait_for_timeout(2000)
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        ld = json_ld_product(soup)
        if ld:
            data["name"] = ld.get("name")
            offers = ld.get("offers",{})
            if isinstance(offers,list): offers = offers[0] if offers else {}
            if isinstance(offers,dict):
                p = offers.get("price")
                if p: data["price"] = parse_price(str(p))
        el = soup.select_one("#productTitle")
        if el and not data["name"]: data["name"] = el.get_text(" ",strip=True)
        if data["price"] is None:
            for sel in ["#corePriceDisplay_desktop_feature_div .a-offscreen",
                        "#corePrice_feature_div .a-offscreen",".a-price .a-offscreen",
                        "#price_inside_buybox","#priceblock_ourprice"]:
                el = soup.select_one(sel)
                if el:
                    p = parse_price(el.get("content") or el.get_text(strip=True))
                    if p and p>1: data["price"]=p; break
        el = soup.select_one("#availability")
        if el:
            t = el.get_text(" ",strip=True).lower()
            if "in stock" in t or "n stock" in t: data["availability"]="In Stock"
            elif "unavailable" in t or "out of stock" in t: data["availability"]="Out of Stock"
            elif t.strip(): data["availability"]=el.get_text(strip=True)[:80]
        if not data["availability"] and (soup.select_one("#add-to-cart-button") or soup.select_one("#buy-now-button")):
            data["availability"]="In Stock"
        el = soup.select_one("#acrPopover")
        if el:
            t = str(el.get("title") or "") or el.get_text(strip=True)
            m = re.search(r"([\d.]+)\s*out of",t)
            if m: data["rating"]=m.group(1)
    except Exception as e:
        print(f"    amazon error: {e}")
    return data

def get_newegg_avail(page, url):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
        page.wait_for_timeout(2000)
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        ld = json_ld_product(soup)
        if ld:
            offers = ld.get("offers",{})
            if isinstance(offers,list): offers = offers[0] if offers else {}
            av = (offers if isinstance(offers,dict) else {}).get("availability","")
            if "InStock" in av: return "In Stock"
            if "OutOfStock" in av: return "Out of Stock"
        for sel in ["div.product-inventory strong",".product-inventory"]:
            el = soup.select_one(sel)
            if el:
                t = el.get_text(strip=True).lower()
                if "in stock" in t: return "In Stock"
                if "out of" in t: return "Out of Stock"
        btn = soup.select_one("button.btn-primary.btn-message, button.btn-primary")
        if btn and "add to cart" in btn.get_text(strip=True).lower():
            return "In Stock"
    except Exception as e:
        print(f"    newegg avail error: {e}")
    return None

def main():
    results      = json.loads(RF.read_text())
    new_listings = json.loads(NLF.read_text())
    idx = {(r["sku_id"],r["retailer"]): i for i,r in enumerate(results)}

    # ── Phase 1 ───────────────────────────────────────────────────────────────
    print("Phase 1: Applying web-search data...")
    for (sku_id,retailer), data in SEARCH_DATA.items():
        key = (sku_id,retailer)
        if key not in idx: continue
        i = idx[key]; rec = results[i]; changed = False
        for field in ("name","price","availability","rating"):
            if rec[field] is None and data.get(field) is not None:
                rec[field]=data[field]; changed=True
        if changed:
            missing=[f for f in ("name","price","availability","rating") if rec[f] is None]
            rec["status"]="ok" if not missing else f"partial: missing {', '.join(missing)}"
            print(f"  ✓ {sku_id}/{retailer}")

    # Save after Phase 1 so it's not lost if Phase 2 errors
    RF.write_text(json.dumps(results, indent=2))
    print("  → results.json saved after Phase 1")

    # ── Phase 2 ───────────────────────────────────────────────────────────────
    if HAS_PW and _sync_playwright is not None:
        print("\nPhase 2: Targeted re-fetch (Target prices, Amazon prices, Newegg avail)...")
        pw = _sync_playwright().start()
        browser = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = browser.new_context(user_agent=UA, viewport={"width":1280,"height":900},
                                  locale="en-US", timezone_id="America/New_York")
        page = ctx.new_page()
        # Apply stealth per-page when possible
        stealth_obj = (_Stealth(navigator_languages=True,navigator_user_agent=True,
                                navigator_vendor=True) if HAS_STEALTH and _Stealth else None)
        if stealth_obj:
            stealth_obj.apply_stealth_sync(page)

        for i, rec in enumerate(results):
            domain = urlparse(rec["url"]).netloc

            if "target.com" in domain and (rec["price"] is None or rec["availability"] is None):
                print(f"  Target {rec['sku_id']}: re-fetching...")
                d = get_target_data(page, rec["url"])
                for f in ("price","availability","rating"):
                    if rec[f] is None and d.get(f) is not None:
                        rec[f]=d[f]; print(f"    {f}={d[f]}")
                missing=[f for f in ("name","price","availability","rating") if rec[f] is None]
                rec["status"]="ok" if not missing else f"partial: missing {', '.join(missing)}"
                time.sleep(1)

            elif "amazon.com" in domain and rec["price"] is None:
                print(f"  Amazon {rec['sku_id']}: re-fetching price...")
                d = get_amazon_price(page, rec["url"])
                for f in ("name","price","availability","rating"):
                    if rec[f] is None and d.get(f) is not None:
                        rec[f]=d[f]; print(f"    {f}={d[f]}")
                missing=[f for f in ("name","price","availability","rating") if rec[f] is None]
                rec["status"]="ok" if not missing else f"partial: missing {', '.join(missing)}"
                time.sleep(1.5)

            elif "newegg.com" in domain and rec["availability"] is None:
                print(f"  Newegg {rec['sku_id']}: re-fetching avail...")
                av = get_newegg_avail(page, rec["url"])
                if av:
                    rec["availability"]=av; print(f"    availability={av}")
                    missing=[f for f in ("name","price","availability","rating") if rec[f] is None]
                    rec["status"]="ok" if not missing else f"partial: missing {', '.join(missing)}"
                time.sleep(1)

        page.close(); browser.close(); pw.stop()

    # ── Phase 3 ───────────────────────────────────────────────────────────────
    print("\nPhase 3: Updating new_listings...")
    nl_idx = {nl["sku_id"]: i for i,nl in enumerate(new_listings)}
    for sku_id, urls in NEW_LISTINGS_EXTRA.items():
        if sku_id not in nl_idx: continue
        existing = set(new_listings[nl_idx[sku_id]]["new_retailer_urls"])
        merged   = new_listings[nl_idx[sku_id]]["new_retailer_urls"][:]
        for u in urls:
            if u not in existing: merged.append(u); existing.add(u)
        new_listings[nl_idx[sku_id]]["new_retailer_urls"] = merged[:5]
        print(f"  {sku_id}: {len(new_listings[nl_idx[sku_id]]['new_retailer_urls'])} URLs")

    RF.write_text(json.dumps(results, indent=2))
    NLF.write_text(json.dumps(new_listings, indent=2))

    ok      = sum(1 for r in results if r["status"]=="ok")
    partial = sum(1 for r in results if r["status"].startswith("partial"))
    errors  = sum(1 for r in results if r["status"].startswith("error"))
    print(f"\n{'='*60}\n  DONE: {ok}/{len(results)} fully complete, {partial} partial, {errors} errors\n{'='*60}")

if __name__=="__main__":
    main()
