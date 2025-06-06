import json
import os
import datetime
import re

# File paths
input_file = "proceedings.json"
output_file = "proceeding_ids.txt"

# Ensure input file exists
if not os.path.exists(input_file):
    print(f"Error: {input_file} does not exist")
    exit(1)

# Function to check if a date is after January 1, 2020
def is_after_jan_2020(date_str):
    try:
        # Handle various date formats
        if not date_str:
            return False
            
        # Try to extract date components using regular expressions
        # Match patterns like "January 15, 2023", "Jan 15, 2023", "01/15/2023", "15-01-2023", etc.
        
        # First try to extract just the year
        year_match = re.search(r'20\d{2}', date_str)
        if year_match:
            year = int(year_match.group(0))
            if year < 2020:
                return False
            elif year > 2020:
                return True
            # If it's exactly 2020, we need to check month and day
            
        # Check for month name formats (e.g., "January 15, 2020" or "Jan 15, 2020")
        month_names = {
            "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, 
            "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, 
            "august": 8, "aug": 8, "september": 9, "sep": 9, "october": 10, "oct": 10, 
            "november": 11, "nov": 11, "december": 12, "dec": 12
        }
        
        # Try different date formats
        formats = [
            "%B %d, %Y",  # January 15, 2020
            "%b %d, %Y",  # Jan 15, 2020
            "%m/%d/%Y",   # 01/15/2020
            "%Y-%m-%d",   # 2020-01-15
            "%d-%m-%Y",   # 15-01-2020
            "%d %B %Y",   # 15 January 2020
            "%d %b %Y",   # 15 Jan 2020
            "%B %Y",      # January 2020
            "%b %Y",      # Jan 2020
            "%m-%Y",      # 01-2020
            "%Y/%m/%d",   # 2020/01/15
        ]
        
        for fmt in formats:
            try:
                date_obj = datetime.datetime.strptime(date_str, fmt)
                return date_obj >= datetime.datetime(2020, 1, 1)
            except ValueError:
                continue
                
        # If none of the formats work, do a more general check
        date_parts = re.findall(r'\b(\d{1,2}|[A-Za-z]+)\b', date_str.lower())
        for part in date_parts:
            if part.isalpha() and part in month_names:
                month = month_names[part]
                if year_match and int(year_match.group(0)) == 2020 and month > 1:
                    return True
        
        # Default to including the proceeding if we can't determine the date
        return False
        
    except Exception as e:
        print(f"Date parsing error for '{date_str}': {str(e)}")
        return False  # Default to not including if we can't parse the date

try:
    # Read the JSON file and extract proceeding IDs
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    # Check if data is a list of proceedings or has a specific structure
    proceeding_ids = []
    
    # Handle different possible JSON structures
    if isinstance(data, list):
        # If it's a list of proceedings
        for item in data:
            if isinstance(item, dict) and 'proceeding_id' in item:
                # Only include if filing date is after Jan 1, 2020
                if 'filing_date' in item and is_after_jan_2020(item['filing_date']):
                    proceeding_ids.append(item['proceeding_id'])
    elif isinstance(data, dict):
        # If it's a dictionary with proceedings
        if 'proceedings' in data and isinstance(data['proceedings'], list):
            for item in data['proceedings']:
                if isinstance(item, dict) and 'proceeding_id' in item:
                    # Only include if filing date is after Jan 1, 2020
                    if 'filing_date' in item and is_after_jan_2020(item['filing_date']):
                        proceeding_ids.append(item['proceeding_id'])
        else:
            # If it's a dictionary with IDs as keys or other structure
            for key, value in data.items():
                # Either the key is the ID or there's an ID field
                if isinstance(value, dict) and 'proceeding_id' in value:
                    # Only include if filing date is after Jan 1, 2020
                    if 'filing_date' in value and is_after_jan_2020(value['filing_date']):
                        proceeding_ids.append(value['proceeding_id'])
    
    # Write the proceeding IDs to the output file
    with open(output_file, 'w', encoding='utf-8') as f:
        for proc_id in proceeding_ids:
            f.write(f"{proc_id}\n")
    
    print(f"Successfully extracted {len(proceeding_ids)} proceeding IDs newer than January 1, 2020 to {output_file}")

except json.JSONDecodeError:
    print(f"Error: {input_file} is not a valid JSON file")
except Exception as e:
    print(f"Error processing file: {str(e)}") 