from selenium import webdriver
from bs4 import BeautifulSoup
import time
import pandas as pd
import chardet
from datetime import datetime, date
import json
import os
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import undetected_chromedriver as uc
import pyautogui
from filelock import FileLock


lock = FileLock("forex_news.csv.lock")


def get_news_source_code(fetch_news=False):
    try:
        file_path = "cred.json"
        temp_path = "cred_temp.json"

        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"user1": {}}

        today_date = datetime.now().day
        # safe default if missing
        seconds_wait = data.get("user1", {}).get("waiting", 5)
        din = data.get("user1", {}).get("news_for_the_day")

        if din == today_date and not fetch_news:
            return True
        else:
            print("inside else!")

        data.setdefault("user1", {})["news_for_the_day"] = today_date

        with open(temp_path, "w", encoding="utf-8") as temp:
            json.dump(data, temp, indent=4)
        os.replace(temp_path, file_path)

        # read chrome location and normalize it
        with open("chrome_location.txt", "r", encoding="utf-8") as cl:
            chrome_profile_path = cl.read().strip()


        normalized_base = chrome_profile_path

        options = uc.ChromeOptions()
        options.add_argument(f"--user-data-dir={normalized_base}")


        options.add_argument("--disable-blink-features=AutomationControlled")
        driver = uc.Chrome(options=options)

        try:
            driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
        except Exception:
            pass

        driver.get("https://www.forexfactory.com/calendar")
        for i in range(10):
            pyautogui.scroll(-500)
        time.sleep(seconds_wait)

        html = driver.page_source
        driver.quit()

        with open("news_source.html", "w", encoding="utf-8") as f:
            f.write(html)

        print("Saved news_source.html")
        return True

    except Exception as e:
        import traceback
        print("❌ Error:", e)
        traceback.print_exc()
        return False




def extract_from_saved_html():
    file_path = "news_source.html"

    # --- Detect encoding first ---
    with open(file_path, "rb") as f:
        raw_data = f.read()
        result = chardet.detect(raw_data)
        encoding = result["encoding"]
        # print(f"Detected encoding: {encoding}")

    # --- Read file safely ---
    with open(file_path, "r", encoding=encoding, errors="replace") as f:
        html_content = f.read()

    # --- Parse HTML ---
    soup = BeautifulSoup(html_content, "html.parser")

    # --- Find all event rows ---
    rows = soup.find_all("tr", class_="calendar__row")
    # print(f"Found {len(rows)} event rows")

    data = []
    current_date = ""
    current_time = ""
    for row in rows:
        
        date_cell = row.find("td", class_="calendar__date")
        time = row.find("td", class_="calendar__time")
        currency = row.find("td", class_="calendar__currency")
        event = row.find("td", class_="calendar__event")
        actual = row.find("td", class_="calendar__actual")
        forecast = row.find("td", class_="calendar__forecast")
        previous = row.find("td", class_="calendar__previous")
        date = ""

        if date_cell:
            date_span = date_cell.find("span", class_="date")
            if date_span:
                date = date_span.get_text(strip=True).replace("\n", " ")
                if date:
                    current_date = date
                   
            else:
                date = current_date
        
        else:
            date = current_date

    
        time = time.get_text(strip=True) if time else ""

        if time:
            current_time = time
        else:
            time = current_time
            

        # --- Extract impact properly (from class name) ---
        impact_value = ""
        impact_cell = row.find("td", class_="calendar__impact")
        if impact_cell:
            span = impact_cell.find("span")
            if span and "class" in span.attrs:
                for c in span["class"]:
                    if "icon--ff-impact-" in c:
                        impact_value = c.replace("icon--ff-impact-", "")
                        break
            elif span and "title" in span.attrs:
                impact_value = span["title"]

        # --- Skip empty rows ---
        if not event:
            continue

        # --- Build dictionary for each row ---
        data.append({
            "date": date,
            "time": time,
            "currency": currency.get_text(strip=True) if currency else "",
            "impact": impact_value.capitalize(),
            "event": event.get_text(strip=True),
            "actual": actual.get_text(strip=True) if actual else "",
            "forecast": forecast.get_text(strip=True) if forecast else "",
            "previous": previous.get_text(strip=True) if previous else "",
        })

    # --- Create DataFrame and save ---
    if data:
        df = pd.DataFrame(data)

        with lock:
            df.to_csv("forex_news.csv", index=False, encoding="utf-8-sig")
        # print(f"✅ Extracted {len(df)} news events and saved to forex_news.csv")
    else:
        print("⚠️ No news events extracted. Check HTML structure or encoding.")

    return data



import pandas as pd
from datetime import datetime, timedelta



def get_usd_red_news(filepath="forex_news.csv", fetch_news = False):
    get_news_source_code(fetch_news)
    extract_from_saved_html()

    # --- Read CSV ---
    with lock:
        df = pd.read_csv(filepath)

    # --- Clean columns ---
    df.columns = df.columns.str.strip()
    df = df.fillna('')
    df['currency'] = df['currency'].astype(str).str.upper().str.strip()
    df['impact'] = df['impact'].astype(str).str.lower().str.strip()
    df['date'] = df['date'].astype(str).str.strip()

    # --- Filter for USD + red (high) impact ---
    red_usd_news = df[
        (df['currency'] == 'USD') &
        (df['impact'].isin(['red', 'high']))
    ]

    # --- Detect today's date ---
    today = datetime.now()
    today_str = today.strftime("%a%b %d")   # e.g. 'ThuNov 06'
    today_str_no_zero = today.strftime("%a%b ").strip() + str(today.day)  # 'ThuNov 6'

    # --- Normalize date formatting and filter ---
    df['date'] = df['date'].str.replace(" ", "")
    today_str_no_space = today_str_no_zero.replace(" ", "")

    red_usd_today = red_usd_news[
        red_usd_news['date'].str.replace(" ", "") == today_str_no_space
    ]

    # --- Drop empty time fields ---
    red_usd_today = red_usd_today[red_usd_today['time'].astype(str).str.strip() != '']

    # --- Sort neatly ---
    red_usd_today = red_usd_today.sort_values(by=['date', 'time']).reset_index(drop=True)

    # print(f"✅ Found {len(red_usd_today)} USD Red-Impact events for today ({today_str_no_zero})")

    return red_usd_today[['date', 'time', 'currency', 'impact', 'event', 'actual', 'forecast', 'previous']]



def extract_news_interval(fetch_news = False):
    with open("cred.json", "r") as creds:
        dt = json.load(creds)

    interval_min = int(dt['user1']['before_after'])  # interval in minutes

    # Assuming get_usd_red_news() returns the filtered dataframe
    df = get_usd_red_news(fetch_news=fetch_news)

    time_list = df['time'].dropna().to_list()
    # print("Original times:", time_list)

    interval_pairs = []

    for t in time_list:
        try:
            # Parse time string like '10:30pm' → datetime object
            t_obj = datetime.strptime(t.strip().lower(), "%I:%M%p")

            # Subtract and add interval
            before_time = (t_obj - timedelta(minutes=interval_min)).strftime("%H:%M")
            after_time = (t_obj + timedelta(minutes=interval_min)).strftime("%H:%M")
            main_time = t_obj.strftime("%H:%M")

            interval_pairs.append({"before": before_time, "after": after_time})

        except ValueError:
            continue

    return interval_pairs


def wait_if_between_news_period(fetch_news = False):
    now_time = datetime.now().time().replace(second=0, microsecond=0)
    inteval = extract_news_interval(fetch_news)

    print(inteval)

    for i in inteval:
        before_str = i['before']
        after_str = i['after']

        before = datetime.strptime(before_str, "%H:%M").time()
        after = datetime.strptime(after_str, "%H:%M").time()

        print(f"before time: {before}, after time: {after}, current_time: {now_time}")
        if now_time > before and now_time < after:
            print("inside the news period")
            now_dt = datetime.combine(date.today(), now_time)
            after_dt = datetime.combine(date.today(), after)
            diff_seconds = (after_dt - now_dt).total_seconds()
            time.sleep(diff_seconds + 2)
        
        else:
            print("outside the news period!")



if __name__ == "__main__":
    df = get_usd_red_news(fetch_news=True)
    print(df)