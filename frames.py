import os # for working with file paths within the OS
import re # for regular expressions
import csv # for working with CSV files
import json # for working with JSON files
import time # for adding delays

from bs4 import BeautifulSoup # for parsing HTML
from selenium import webdriver # for controlling the web browser
from selenium.webdriver.chrome.service import Service # for managing the ChromeDriver service
from selenium.webdriver.chrome.options import Options # for configuring Chrome options
from selenium.webdriver.common.by import By # for locating elements on the page
from selenium.webdriver.support.ui import WebDriverWait # for waiting for elements to load
from selenium.webdriver.support import expected_conditions as EC # for defining expected conditions
from selenium.common.exceptions import TimeoutException # for handling timeout exceptions
from webdriver_manager.chrome import ChromeDriverManager # for automatically managing the ChromeDriver binary

# Configuration I
BASE_URL = "https://www.framesdirect.com/eyeglasses/"
OUTPUT_DIR = "./extracted_data"
BASE_FILE_NAME = "framesdirect_data"
MAX_PAGES = 10  # Maximum number of pages to scrape
TIMEOUT = 20
SCROLL_PASSES = 10 # Number of times to scroll down the page to load more products
SOURCE = "framesdirect"

FIELDNAMES = ["source", "brand", "name", "former_price", "current_price", "discount", "product_link", "page"]

# HELPER FUNCTIONS
def price_to_float(raw):
    """'$129.95' -> 129.95 ; empty or non-numeric -> None."""
    if not raw:
        return None
    match = re.search(r"\d[\d,]*(?:\.\d+)?", raw.replace(",", ""))
    return float(match.group()) if match else None


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

# Configuration II: Browser Setup
csv_path, json_path = start_files(OUTPUT_DIR, BASE_FILE_NAME, FIELDNAMES)

print("Setting up WebDriver...")
chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.6778.265 Safari/537.36"
)
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()),
            options=chrome_options)
print("WebDriver setup complete.")

# Main Scraping Logic
glasses_data = []
seen_products = set()

try:
    for page_num in range(1, MAX_PAGES + 1):
        url = BASE_URL if page_num == 1 else f"{BASE_URL}?p={page_num}"
        print(f"\n[page {page_num}] {url}")
        driver.get(url)

        try:
            WebDriverWait(driver, TIMEOUT).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.prod-holder"))
            )
        except TimeoutException:
            print(f"[page {page_num}] no tiles appeared - end of results.")
            break

        # Scroll until the tile count stops growing (lazy loading)
        previous_count = -1
        for _ in range(SCROLL_PASSES):
            tiles = driver.find_elements(By.CSS_SELECTOR, "div.prod-holder")
            if len(tiles) == previous_count:
                break
            previous_count = len(tiles)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        container = soup.find("div", id="product-list-container") or soup
        all_products = container.find_all("div", class_="prod-holder")

        if not all_products:
            print(f"[page {page_num}] container empty - stopping.")
            break

        print(f"[page {page_num}] {len(all_products)} tiles in DOM")

        page_rows = []
        for product in all_products:
            title_block = product.find("div", class_="prod-title")
            price_block = product.find("div", class_="prod-bot")
            if not (title_block and price_block):
                continue

            name_tag = title_block.find("div", class_="product_name")
            name = name_tag.get_text(strip=True) if name_tag else None

            brand_tag = title_block.find("div", class_="catalog-name")
            brand = brand_tag.get_text(strip=True) if brand_tag else None

            former_tag = price_block.find("div", class_="prod-catalog-retail-price")
            former_price = price_to_float(former_tag.get_text(strip=True)) if former_tag else None

            current_tag = price_block.find("div", class_="prod-aslowas")
            current_price = price_to_float(current_tag.get_text(strip=True)) if current_tag else None

            discount_tag = price_block.find("div", class_=re.compile(r"frame-discount"))
            discount = None
            if discount_tag:
                discount = re.sub(r"\s*off\s*", "", discount_tag.get_text(strip=True),
                                  flags=re.IGNORECASE).strip() or None

            link_tag = product.find("a", href=True)
            product_link = link_tag["href"] if link_tag else None
            if product_link and product_link.startswith("/"):
                product_link = "https://www.framesdirect.com" + product_link

            # Dedupe: a bad page param can silently re-serve page 1
            fingerprint = (brand, name, current_price)
            if fingerprint in seen_products:
                continue
            seen_products.add(fingerprint)

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
            glasses_data.append(row)

        # Save the data
        flush_batch(page_rows, glasses_data, csv_path, json_path,
                    FIELDNAMES, label=f"[page {page_num}]")

        if not page_rows:
            print("No new products - reached the end.")
            break

        time.sleep(1)  # be polite

finally:
    driver.quit()
    print(f"\nWebDriver closed. {len(glasses_data)} records in {csv_path} and {json_path}")