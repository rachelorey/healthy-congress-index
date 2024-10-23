from lxml import html
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
import sys
import os

sys.path.append(os.path.abspath("..\working_days"))
import workingdays_helper

def get_item_by_name(amendment,name):
    # Locate all spans with class 'result-item'
    all_spans = amendment.find_all('span', class_='result-item')

    # Iterate through all the spans to find the one with given name
    response_item = "N/A"  # fallback
    for span in all_spans:
        strong_tag = span.find('strong')
        if strong_tag and name in strong_tag.text:
            # get text
            if name == "Latest Action:": # for latest action, want all text (not just <a>)
                response_item = span.text.strip().split("\n")[1].strip()
            else: # get the <a> tag's text
                response_item = span.find('a').text.strip()
            break

    return response_item

# Function to process the outcome based on the 'Latest Action' field
def determine_outcome(latest_action):
    if pd.isna(latest_action):  # Check if latest_action is NaN
        return "INPUT BY HAND"
    if "not agreed" in latest_action.lower():
        return "NA"  # Not Agreed
    else:
        return "A"  # Agreed

# Function to process the action type based on the 'Latest Action' field
def determine_action_type(latest_action):
    if pd.isna(latest_action):  # Check if latest_action is NaN
        return "INPUT BY HAND"
    if "unanimous" in latest_action.lower():
        return "UC"  # Unanimous Consent
    elif "Yea-Nay" in latest_action:
        return "RCV"  # Roll Call Vote
    elif "Voice Vote" in latest_action:
        return "VV"  # Voice Vote
    else:
        return "INPUT BY HAND"  # Error if not matched

# Function to handle pagination and scrape each page
def scrape_amendments(start_date, end_date=None):
    # Set start and end dates
    if end_date is None:
        dateend = datetime.now().date()       
    else:
        dateend = datetime.strptime(end_date, '%m/%d/%Y').date()
    datestart = datetime.strptime(start_date, '%m/%d/%Y').date()

    formatted_start = str(datestart.strftime("%Y-%m-%d"))+"%22%20TO%20%22"
    formatted_end = str(dateend.strftime('%Y-%m-%d'))

    # Initialize data list for storing results
    data_list = []
    
    # Initialize pagination
    page_number = 1
    base_url = f"https://www.congress.gov"
    next_url = (f"/advanced-search/command-line?query=actionCode:(94000%20OR%2095000)%20"
                f"latestActionDateStr:[%22{formatted_start}{formatted_end}%22]%20billType:%22SAmdt%22"
                f"&searchResultViewType=compact&KWICView=false&pageSize=250&page={page_number}")
    
    while True:
        # Construct the full URL
        url = f"{base_url}{next_url}"
        
        # Scrape the page using Selenium
        tree = workingdays_helper.scrape_w_selenium(url)

        # Convert lxml tree to BeautifulSoup for easy parsing
        page_content = html.tostring(tree, pretty_print=True).decode()
        soup = BeautifulSoup(page_content, 'html.parser')

        # Scraping logic to extract the amendment information
        amendments = soup.find_all('li', class_='expanded')

        # If no amendments are found, break the loop
        if not amendments:
            break

        for amendment in amendments:
            try:
                # Extract amendment number and congress separately
                amendment_heading = amendment.find('span', class_='amendment-heading')
                first_url = amendment_heading.find('a')['href'].strip()

                # Extract the full text of the span
                full_text = amendment_heading.get_text(strip=False)

                # Handle cases with "to" (i.e., ranges) or just a single amendment number
                if "to" in full_text:
                    amendment_number = full_text.split("—")[0].strip().replace("\n","")  # Get the entire text if it contains "to"
                else:
                    amendment_number = amendment_heading.find('a').text.strip()

                # amendment_number = amendment.find('span', class_='amendment-heading').find('a').text.strip()  # S.Amdt.No
                congress_info = amendment.find('span', class_='amendment-heading').text.strip().split('—')[1].strip()  # Congress info

                # Extract amends bill
                amends_bill = get_item_by_name(amendment, "Amends Bill:")
                sponsor = get_item_by_name(amendment, "Sponsor:")
                action = get_item_by_name(amendment, "Latest Action:")

                # Append data to the list
                data_list.append({
                    "Congress":congress_info if congress_info else "N/A",
                    "S.Amdt.No": amendment_number if amendment_number else "N/A",
                    "Amends": amends_bill if amends_bill else "N/A",
                    "Sponsor": sponsor if sponsor else "N/A",
                    "Latest Action": action if action else "N/A",
                    "url":"congress.gov"+first_url if first_url else "N/A"
                })

            except Exception as e:
                print(f"Error processing amendment: {e}")

        # Check if there's a "Next" button
        next_button = soup.find('a', class_='next')
        if next_button:
            next_url = next_button['href']  # Update to the next page URL
        else:
            break  # Exit the loop if no next page is available

        # Increment the page number
        page_number += 1

    # Convert the list of data into a DataFrame
    df = pd.DataFrame(data_list)

    # post processing

    # seperate latest action date from action description
    df[['Latest Action Date', 'Latest Action']] = df['Latest Action'].str.extract(r'(\d{2}/\d{2}/\d{2}) (.+)')

    # extract party
    df['Sponsor Party'] = df['Sponsor'].str.extract(r'\[Sen\.-([RD])')

    # Check if 'Outcome' and 'Action Type' columns exist, if not create them
    if 'Outcome' not in df.columns:
        df['Outcome'] = pd.NA
    if 'Action Type' not in df.columns:
        df['Action Type'] = pd.NA

    # Ensure 'Outcome' and 'Action Type' columns are of object type (for strings)
    df['Outcome'] = df['Outcome'].astype('object')
    df['Action Type'] = df['Action Type'].astype('object')

    for i, amendment in df.iterrows():
        try:
            latest_action = amendment['Latest Action']
            outcome = determine_outcome(latest_action)
            action_type = determine_action_type(latest_action)

            df.loc[i, 'Outcome'] = outcome
            df.loc[i, 'Action Type'] = action_type

        except Exception as e:
            print(f"Error processing amendment {df.iloc[i]}: {e}")

    # if "to" is in S.Amdt.No, replace the current value in Amends with the split("to")[1]
    for i, row in df.iterrows():
        if "to" in row["S.Amdt.No"]:
            df.loc[i, "Amends"] = row["S.Amdt.No"].split("to")[1].strip()
            df.loc[i, "S.Amdt.No"] = row["S.Amdt.No"].split("to")[0].strip()
            
    # Return the DataFrame
    return df