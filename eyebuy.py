# =============================================================================
# EyeBuyDirect.com eyeglasses scraper
# Pagination: path segments - /eyeglasses, /eyeglasses-page-2, ...
# Saves after every page. Schema matches framesdirect.py for the unifier.
# =============================================================================

import os
import re
import csv
import json
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

# ------------------------------- Config --------------------------------------
BASE = "https://www.eyebuydirect.com"
LISTING_URL = f"{BASE}/eyeglasses"
OUTPUT_DIR = "./extracted_data"
BASENAME = "eyebuydirect_data"
SOURCE = "eyebuydirect"
DEFAULT_BRAND = "EyeBuyDirect"
MAX_PAGES = 10
WAIT_TIMEOUT = 20
SCROLL_PASSES = 12

FIELDNAMES = ["source", "brand", "name", "former_price", "current_price",
              "discount", "product_link", "page"]


# ------------------------------ Helpers --------------------------------------
def price_to_float(raw):
    """'$124' -> 124.0 ; empty or non-numeric -> None."""
    if not raw:
        return None
    match = re.search(r"\d[\d,]*(?:\.\d+)?", raw.replace(",", ""))
    return float(match.group()) if match else None


def clean_text(node):
    """Stripped text from a node, or None if missing or empty."""
    if node is None:
        return None
    return node.get_text(" ", strip=True) or None


def start_files(output_dir, basename, fieldnames):
    """Clear any previous run and write a fresh CSV header."""
    os.makedirs(output_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, f"{basename}.csv")
    json_path = os.path.join(output_dir, f"{basename}.json")

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=fieldnames).writeheader()
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump([], f)

    return csv_path, json_path


def flush_batch(rows, all_rows, csv_path, json_path, fieldnames, label=""):
    """Append this page's rows to CSV, rewrite JSON with the full set so far."""
    if not rows:
        print(f"  {label} nothing new to save")
        return

    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=fieldnames).writerows(rows)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, indent=4)

    print(f"  {label} saved {len(rows)} rows (file total: {len(all_rows)})")


# --------------------------- Step 1: Setup -----------------------------------
csv_path, json_path = start_files(OUTPUT_DIR, BASENAME, FIELDNAMES)

print("Setting up WebDriver...")
chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--lang=en-US,en")
chrome_options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.6778.265 Safari/537.36"
)
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option("useAutomationExtension", False)
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()),
                          options=chrome_options)

all_data = []
seen_links = set()

# ------------------- Steps 2-4: Paginate, parse, save ------------------------
try:
    for page_num in range(1, MAX_PAGES + 1):
        url = LISTING_URL if page_num == 1 else f"{BASE}/eyeglasses-page-{page_num}"
        print(f"\n[page {page_num}] {url}")
        driver.get(url)

        try:
            WebDriverWait(driver, WAIT_TIMEOUT).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'div[class*="__product-card"]'))
            )
        except TimeoutException:
            print(f"[page {page_num}] no tiles rendered - end of results.")
            break

        if page_num == 1:
            for label in ("Accept", "Accept All", "Got it", "Continue"):
                try:
                    driver.find_element(By.XPATH, f"//button[contains(., '{label}')]").click()
                    time.sleep(1)
                    break
                except Exception:
                    pass

        # Scroll until the tile count stops growing (images are loading="lazy")
        previous_count = -1
        for _ in range(SCROLL_PASSES):
            tiles = driver.find_elements(By.CSS_SELECTOR, 'div[class*="__product-card"]')
            if len(tiles) == previous_count:
                break
            previous_count = len(tiles)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        grid = soup.select_one('div[class*="__product-grid"]') or soup
        all_products = grid.select('div[class*="__product-card"]')

        if not all_products:
            print(f"[page {page_num}] grid empty - stopping.")
            break

        print(f"[page {page_num}] {len(all_products)} tiles in DOM")

        page_rows = []
        for product in all_products:
            link_tag = product.select_one('a[class*="__item-img-link"]')
            product_link = urljoin(BASE, link_tag["href"]) if link_tag and link_tag.get("href") else None

            name_block = product.select_one('[class*="__item-name"]')
            name = clean_text(name_block)
            if not name and name_block:
                anchor = name_block.find("a")
                name = anchor.get("title") if anchor else None

            # Brand appears as <img alt="tag-Ray-Ban">, absent on house frames
            brand = None
            brand_block = product.select_one('[class*="__item-brands"]')
            if brand_block:
                brand_img = brand_block.find("img")
                if brand_img and brand_img.get("alt"):
                    candidate = re.sub(r"^tag-", "", brand_img["alt"], flags=re.IGNORECASE).strip()
                    if candidate.lower() not in ("kids", "new", "sale", "ai-glasses"):
                        brand = candidate or None
            brand = brand or DEFAULT_BRAND

            # <ins> is what you pay, <del> is the RRP and only exists on sale items
            price_block = product.select_one('[class*="__price-wrapper"]')
            current_price = former_price = None
            if price_block:
                current_price = price_to_float(clean_text(price_block.select_one('ins[class*="__price"]')))
                former_price = price_to_float(clean_text(price_block.select_one('del[class*="__retail"]')))

            discount = clean_text(product.select_one('[class*="__tag-off"]'))
            if discount:
                discount = re.sub(r"\s*off\s*", "", discount, flags=re.IGNORECASE).strip() or None
            if discount is None and former_price and current_price and former_price > current_price:
                discount = f"{round((former_price - current_price) / former_price * 100)}%"

            if not name and current_price is None:
                continue

            if product_link:
                if product_link in seen_links:
                    continue
                seen_links.add(product_link)

            row = {
                "source": SOURCE,
                "brand": brand,
                "name": name,
                "former_price": former_price,
                "current_price": current_price,
                "discount": discount,
                "product_link": product_link,
                "page": page_num,
            }
            page_rows.append(row)
            all_data.append(row)

        flush_batch(page_rows, all_data, csv_path, json_path,
                    FIELDNAMES, label=f"[page {page_num}]")

        if not page_rows:
            print("No new products - reached the end.")
            break

        time.sleep(1)

finally:
    driver.quit()
    print(f"\nWebDriver closed. {len(all_data)} records in {csv_path} and {json_path}")
    