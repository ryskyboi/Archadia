from selenium.webdriver.chrome.webdriver import WebDriver as ChromeDriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

import time
import pandas as pd
import logging
from tqdm import tqdm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ScrapeLeaderboard:
    def __init__(self, driver_path: str, url: str):
        self.service = Service(executable_path=driver_path)
        self.url = url

    def get_table_data(self, driver: ChromeDriver) -> list[list[str]]:
        try:
            # Wait for table to load
            wait = WebDriverWait(driver, 20)  # Increased timeout
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "tbody")))
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "td")))  # Make sure cells are loaded

            time.sleep(2)  # Small buffer to ensure complete loading

            # Get all rows from the table body
            rows = driver.find_elements(By.CSS_SELECTOR, "tbody > tr")
            # logger.info(f"Found {len(rows)} rows")

            if not rows:
                logger.error("No rows found in table")
                return []

            data = []
            for row_idx, row in enumerate(rows):
                try:
                    # Get all cells in the row
                    cells = row.find_elements(By.TAG_NAME, "td")

                    # Extract text from each cell
                    row_data = []
                    for i, cell in enumerate(cells):
                        if i == 4:  # Owner column
                            row_data.append(cell.text)
                        elif i == 5:  # Skip Explorer column
                            continue
                        else:
                            row_data.append(cell.text)

                    #logger.info(f"Row {row_idx + 1}: {row_data}")
                    if len(row_data) == 5:  # Make sure we have all required columns
                        data.append(row_data)
                    else:
                        logger.warning(f"Row {row_idx + 1} has incorrect number of columns: {len(row_data)}")

                except Exception as e:
                    logger.error(f"Error processing row {row_idx + 1}: {str(e)}")
                    continue

            return data

        except TimeoutException:
            logger.error("Timeout waiting for table to load")
            return []
        except Exception as e:
            logger.error(f"Error in get_table_data: {str(e)}")
            return []

    def scroll_to_element(self, driver: ChromeDriver, element) -> None:
        try:
            # First scroll the element into view
            driver.execute_script("arguments[0].scrollIntoView(true);", element)
            time.sleep(1)  # Wait for initial scroll

            # Then scroll up a bit to avoid footer and ensure element is in a good clicking position
            driver.execute_script("window.scrollBy(0, -200);")
            time.sleep(1)
            
            # Try to remove any overlaying elements
            driver.execute_script("""
                // Remove footer
                var elements = document.getElementsByClassName('css-14tds1b');
                for(var i=0; i<elements.length; i++) {
                    elements[i].style.display = 'none';
                }
                
                // Remove any other fixed position elements that might interfere
                var fixed = document.querySelectorAll('*');
                for(var i=0; i<fixed.length; i++) {
                    var style = window.getComputedStyle(fixed[i]);
                    if(style.position === 'fixed' || style.position === 'sticky') {
                        fixed[i].style.display = 'none';
                    }
                }
            """)
            time.sleep(1)

            # Final check - ensure element is in viewport and clickable
            rect = driver.execute_script("""
                var rect = arguments[0].getBoundingClientRect();
                return {
                    top: rect.top,
                    bottom: rect.bottom,
                    height: rect.height,
                    windowHeight: window.innerHeight
                };
            """, element)

            # If element is not in a good position, adjust scroll
            if rect['top'] < 0 or rect['bottom'] > rect['windowHeight']:
                driver.execute_script(
                    "window.scrollTo(0, arguments[0].offsetTop - (window.innerHeight / 2));",
                    element
                )
                time.sleep(1)

        except Exception as e:
            logger.error(f"Error scrolling to element: {str(e)}")

    def scrape(self) -> list[list[str]]:
        driver = None
        try:
            driver = ChromeDriver(service=self.service)
            driver.get(self.url)

            logger.info("Getting initial table data")
            all_data = self.get_table_data(driver)

            try:
                # Get total pages from pagination text
                wait = WebDriverWait(driver, 10)
                pagination = wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//p[contains(text(), 'Page')]")))
                total_pages = int(pagination.text.split('of')[-1].strip())
                #logger.info(f"Total pages: {total_pages}")

                # Click through remaining pages
                for page in tqdm(range(2, total_pages + 1), desc="Processing pages"):
                    try:
                        #logger.info(f"Processing page {page}")
                        next_button = wait.until(EC.element_to_be_clickable(
                            (By.XPATH, "//button[text()='>']")))
                        self.scroll_to_element(driver, next_button)
                        next_button.click()
                        time.sleep(3)  # Wait for page load
                        page_data = self.get_table_data(driver)
                        all_data.extend(page_data)
                    except Exception as e:
                        logger.error(f"Error processing page {page}: {str(e)}")
                        break

            except Exception as e:
                logger.error(f"Error in pagination: {str(e)}")

            return all_data

        except Exception as e:
            logger.error(f"Error in scrape: {str(e)}")
            return []

        finally:
            if driver:
                driver.quit()

    def scrape_to_df(self) -> pd.DataFrame:
        try:
            data = self.scrape()
            if not data:
                logger.error("No data collected")
                return pd.DataFrame()

            df = pd.DataFrame(data, columns=['Rank', 'Points', 'Referrals', 'Points from Referrals', 'Owner'])

            # Clean up numeric columns
            df['Rank'] = pd.to_numeric(df['Rank'], errors='coerce')
            df['Points'] = pd.to_numeric(df['Points'].str.replace(',', ''), errors='coerce')
            df['Referrals'] = pd.to_numeric(df['Referrals'], errors='coerce')
            df['Points from Referrals'] = pd.to_numeric(df['Points from Referrals'].str.replace(',', ''), errors='coerce')

            df.to_csv('points_leaderboard.csv', index=False)
            logger.info(f"Saved {len(df)} rows to CSV")
            return df

        except Exception as e:
            logger.error(f"Error in scrape_to_df: {str(e)}")
            return pd.DataFrame()
