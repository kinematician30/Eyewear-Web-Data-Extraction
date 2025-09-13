import json
import csv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

def setup_webdriver():
    """Sets up and returns a configured Selenium WebDriver."""
    print("Setting up WebDriver...")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.265 Safari/537.36"
    )

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def extract_product_data(html_source):
    """Parses the HTML source and extracts product data."""
    soup = BeautifulSoup(html_source, "html.parser")
    product_tiles = soup.find_all('a', class_='product-tile')
    
    products_to_add = []
    
    for tile in product_tiles:
        product_info = tile.find('div', class_='product-info')
        if product_info:
            brand_tag = product_info.find('div', class_='product-brand')
            brand = brand_tag.text.strip() if brand_tag else None
            
            name_tag = product_info.find('div', class_='product-code')
            name = name_tag.text.strip() if name_tag else None
            
            price_container = product_info.find('div', class_='product-prices')
            if price_container:
                former_price_tag = price_container.find('div', class_='product-list-price')
                former_price = former_price_tag.text.strip() if former_price_tag else None
                
                current_price_tag = price_container.find('div', class_='product-offer-price')
                current_price = current_price_tag.text.strip() if current_price_tag else None
            else:
                former_price, current_price = None, None

            discount_tag = tile.find('div', class_='product-badge discount-badge thirty')
            discount = discount_tag.text.strip() if discount_tag else None
            
            data = {
                'brand': brand,
                'name': name,
                'former_price': former_price,
                'current_price': current_price,
                'discount': discount
            }
            products_to_add.append(data)
            
    return products_to_add

def save_data_to_files(data, json_filename='./extracted_data/glasses_data.json', csv_filename='./extracted_data/glasses_data.csv'):
    """Saves the extracted data to both JSON and CSV files."""
    if not data:
        print("No data to save.")
        return

    # Deduplicate the data
    final_data = [dict(t) for t in {tuple(d.items()) for d in data}]
    
    # Save to JSON
    with open(json_filename, 'w') as json_file:
        json.dump(final_data, json_file, indent=4)
    print(f"Data successfully saved to {json_filename}.")

    # Save to CSV
    if final_data:
        keys = final_data[0].keys()
        with open(csv_filename, 'w', newline='', encoding='utf-8') as csv_file:
            dict_writer = csv.DictWriter(csv_file, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(final_data)
        print(f"Data successfully saved to {csv_filename}.")

# Main execution flow
if __name__ == "__main__":
    driver = setup_webdriver()
    base_url = "https://www.glasses.com"
    url = f"{base_url}/gl-us/eyeglasses?"
    all_products_data = []

    try:
        while url:
            print(f"Visiting URL: {url}")
            driver.get(url)
            
            try:
                print("Waiting for product tiles to load...")
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "catalog-page"))
                )
            except Exception as e:
                print(f"Error waiting for page to load: {e}")
                driver.quit()
                exit()

            # Get page source and extract data
            html_source = driver.page_source
            products_on_page = extract_product_data(html_source)
            all_products_data.extend(products_on_page)
            print(f"Extracted {len(products_on_page)} products. Total so far: {len(all_products_data)}")

            # Find the next page link
            soup = BeautifulSoup(html_source, "html.parser")
            next_link_element = soup.find('div', class_='load-more-wrapper', attrs={'data-filter-url': True})
            
            if next_link_element and 'data-filter-url' in next_link_element.attrs:
                next_url_path = next_link_element['data-filter-url']
                url = f"{next_url_path}"
                print(f"Found next page URL: {url}")
                # Save the incremental progress
                save_data_to_files(all_products_data)
            else:
                print("No more pages found.")
                url = None # End the loop
                
        # Final save after the loop completes
        save_data_to_files(all_products_data)

    finally:
        driver.quit()
        print("\nScraping complete. WebDriver closed.")