import json
from datetime import datetime, timedelta
import re
import calendar
from bson import json_util
from dotenv import load_dotenv
from urllib.parse import quote_plus
import os
from pymongo import MongoClient


# Function to extract date range dynamically
dotenv_path = os.path.join(os.getcwd(), ".env")  # Ensure correct path
load_dotenv(dotenv_path)

USERNAME = quote_plus(os.getenv("MONGO_USER", "default_user"))
PASSWORD = quote_plus(os.getenv("MONGO_PASS", "default_pass"))
CLUSTER = os.getenv("MONGO_CLUSTER", "cluster0")

uri = f"mongodb+srv://{USERNAME}:{PASSWORD}@{CLUSTER}.stgq1pn.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
#print(uri)
client = MongoClient(uri)
# MongoDB client setup
db = client["crm_system"]  
collection = db["call_logs"] 

#constants defined
COUNT_WORDS = {"count", "number", "how many", "total"}
STATUS_SYNONYMS = {
    "completed": {"completed", "successful", "done", "finished", "complete"},
    "failed": {"failed", "unsuccessful", "dropped", "not completed", "fail"},
    "missed": {"missed", "not answered", "ignored", "blown off", "miss"}
}
# Weekday mapping
WEEKDAYS = {
    "sunday": 1, "monday": 2, "tuesday": 3, "wednesday": 4,
    "thursday": 5, "friday": 6, "saturday": 7
}

def find_specific_weekday(start, end, day, query):
    """find occurences of specific weekday in given range"""
    curr_date=start
    
    today=datetime.now()
    match_dates=[]
    if start is not None and end is not None:
        while curr_date<=end:
            if curr_date.weekday()==day:
                match_dates.append(curr_date)
            curr_date+=timedelta(days=1)
        end=match_dates[-1]
        start=match_dates[0]
     
    if "last" in query and query.strip().lower() in ["last monday", "last tuesday", "last wednesday", 
                                                 "last thursday", "last friday", "last saturday", "last sunday"]:
        if start is None and end is None:
            # Find last occurrence of the target weekday
            days_ago = (today.weekday() - day + 7) % 7 or 7
            start = today - timedelta(days=days_ago)
        else:
            start=match_dates[-1]
            end=start

    elif "this" in query and query.strip().lower() in ["this monday", "this tuesday", "this wednesday", 
                                                 "this thursday", "this friday", "this saturday", "this sunday"]:
        # Find the most recent occurrence (or today if it's the same day)
        if start is None and end is None:
            # Find last occurrence of the target weekday
            days_ago = (today.weekday() - day + 7) % 7 
            start = today - timedelta(days=days_ago)
        else:
            start=match_dates[-1]
            end=start
    
   
    return start, end

def get_date_range(query):
    query=query.lower()
    today = datetime.now()
    date_pattern = r'(\d{4}-\d{2}-\d{2}|\d{2}-\d{2}-\d{4})'
    match = re.findall(date_pattern, query)
    if len(match) > 2:
        return None, None 

    if len(match) == 2:
        try:
            start_date = datetime.strptime(match[0], "%Y-%m-%d").strftime("%Y-%m-%dT00:00:00Z")
            end_date = datetime.strptime(match[1], "%Y-%m-%d").strftime("%Y-%m-%dT23:59:59Z")
            return start_date, end_date
        except ValueError:
            return None, None
        
    if len(match)==1:    
        print("length:", 1)
        try:
            parsed_date = datetime.strptime(match[0], "%Y-%m-%d")
            return parsed_date.strftime("%Y-%m-%dT00:00:00Z"), parsed_date.strftime("%Y-%m-%dT23:59:59Z")
        except ValueError:
            return None, None
        

    if "this week" in query:
        start_date = today - timedelta(days=today.weekday())
        end_date=today
    elif "this month" in query:
        start_date = today.replace(day=1)
        end_date=today.strftime("%Y-%m-%d")
    elif "yesterday" in query:
        start_date = today - timedelta(days=1)
        end_date=start_date
    elif "last week" in query:
        start_date = today - timedelta(days=today.weekday()) - timedelta(days=7)
        end_date = start_date + timedelta(days=6)
    elif "last month" in query:
        last_month = today.month - 1 if today.month > 1 else 12
        year = today.year if today.month > 1 else today.year - 1
        start_date = datetime(year, last_month, 1)
        end_date = datetime(year, last_month, calendar.monthrange(year, last_month)[1])

    #elif "last year" in query:
    #    start_date = today.replace(year=today.year - 1, month=1, day=1)
    #    end_date = today.replace(year=today.year - 1, month=12, day=31)''''
    
    else:
        # Dynamic "X days ago"
        match = re.search(r'(\d+)\s*days', query)
        if match:
            days = int(match.group(1))
            start_date = today - timedelta(days=days)
            end_date= today
        else:
            start_date= None
            end_date=None  # Invalid date range
    if start_date is not None and end_date is not None:
        return start_date.strftime("%Y-%m-%dT00:00:00Z"), end_date.strftime("%Y-%m-%dT23:59:59Z") 
    return None, None

def normalize_query(query):
    query = query.lower()
    
    # Expand synonyms to include more terms
    synonyms = {
        "discover": "get",
        "show": "get",
        "find": "get",
        "retrieve": "get",
        "stopping_point": "this",
        "past": "last",
        "seven ": "7 ",
        "thirty": "30 ",
        "five": "5",
        "three": "3",
        "ten": "10",
        "unanswered": "missed",
        "highest":"frequent",
        "most":"frequent",
        "common":"frequent"
    }

    for word, replacement in synonyms.items():
        query = query.replace(word, replacement)

    return query

def extract_agents(query):
    agents = collection.distinct("agent")  # This will return a list of unique agent values
    query = query.lower()
    for agent in agents:
        if agent.lower() in query:  # Check if agent's name is in the query
            return agent
    return None

def extract_customers(query):
    
    customers = collection.distinct("customer")  # This will return a list of unique customer values
    query=query.lower()
    for c in customers:
        if c.lower() in query:
            return c

def get_status_synonym(word):
    """Finds a status category based on synonyms."""
    word = word.lower()
    for status, synonyms in STATUS_SYNONYMS.items():
        if word in synonyms:
            return status
    return None

def extract_call_status(query):
    query = query.lower().split()
    for word in query:
        status = get_status_synonym(word)
        if status:
            return status
    return None 

def extract_duration(query):
    """Extracts call duration if mentioned."""
    try:
        match = re.search(r"(\d+)\s*minutes?", query)
        return int(match.group(1)) if match else None
    except Exception as e:
        print(f"Error extracting duration: {e}")
        return None

def extract_time_range(query):
    query = query.lower()
    #will detect everything like 5pm 5 p.m 5 PM
    pattern = (
        r'(?P<hour12>\d{1,2})(?::(?P<minute12>\d{1,2}))?\s*(?P<period>a\.?m\.?|p\.?m\.?)?'
        r'|(?P<hour24>\d{1,2}):(?P<minute24>\d{2})'
    )
    matches = re.finditer(pattern, query, re.IGNORECASE)


    #to detect queries where in the morning or evening is given
    time_aliases = {
        "morning": {"$gte": "06:00:00", "$lt": "12:00:00"},
        "afternoon": {"$gte": "12:00:00", "$lt": "17:00:00"},
        "evening": {"$gte": "17:00:00", "$lt": "20:00:00"},
        "night": {"$gte": "20:00:00", "$lt": "23:59:59"},
    }

    times = []
    # Extract times
    for match in matches:
        d = match.groupdict()
        # Check if the 24-hour format groups were matched.
        if d.get("hour24"):
            hour = int(d["hour24"])
            minute = int(d["minute24"])
        # Otherwise, use the 12-hour format groups.
        elif d.get("hour12"):
            hour = int(d["hour12"])
            minute = int(d["minute12"]) if d.get("minute12") else 0
            period = d.get("period")
            if period:
                period = period.lower()
                if "p" in period and hour != 12:
                    hour += 12
                elif "a" in period and hour == 12:
                    hour = 0
        else:
            continue  # Skip if no valid time group is found.

        time_str = f"{hour:02}:{minute:02}:00"
        times.append(time_str)
        print(times)



    # Check if query mentions morning/evening, etc.
    for alias, time_range in time_aliases.items():
        if alias in query:
            return time_range

    # Handling "after", "before", and "between"
    if "after" in query and times:
        return {"$gte": times[0], "$lt":"23:59:59"}
    elif "before" in query and times:
        print("before", times[0])
        return {"$lt": times[0], "$gte":"00:00:00"}
    elif "between" in query and len(times) == 2:
        return {"$gte": times[0], "$lt": times[1]}

    return times 

def adjust_time_condition(time_condition, start_date, end_date):
    """
    Adjusts the extracted time condition for both date-based and time-only queries.
    - If a date range exists, apply the time condition within that date range.
    - If no date is provided, apply time condition independently.
    """

    if not time_condition:
        return None
    
    adjusted_condition = {}

    # Case 1: If a date range is given, apply time condition within the date range
    if start_date is not None and end_date is not None:
        start_datetime = datetime.strptime(start_date, "%Y-%m-%dT00:00:00Z")
        end_datetime = datetime.strptime(end_date, "%Y-%m-%dT23:59:59Z")

        if "$gte" in time_condition:
            adjusted_condition["$gte"] = start_datetime.replace(
                hour=int(time_condition["$gte"].split(':')[0]),
                minute=int(time_condition["$gte"].split(':')[1]),
                second=0
            ).strftime("%Y-%m-%dT%H:%M:%SZ")

        if "$lt" in time_condition:
            adjusted_condition["$lt"] = end_datetime.replace(
                hour=int(time_condition["$lt"].split(':')[0]),
                minute=int(time_condition["$lt"].split(':')[1]),
                second=59
            ).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Case 2: If no date is given, filter only by time (ignoring the date part)
    # Case 2: No date range → Filter only by time (MongoDB $expr)
    elif start_date is None and end_date is None:
        expr_conditions = []
        if "$gte" in time_condition:
            start_hour=int(time_condition["$gte"].split(':')[0])
            start_minute=int(time_condition["$gte"].split(':')[1])
            
            print(start_hour)
            expr_conditions.append({
                "$or": [{ "$gte": [ { "$hour": { "$dateFromString": { "dateString" :"$call_time"} } }, start_hour]},
                    {
                        "$and": [
                            { "$eq": [{ "$hour": { "$dateFromString": { "dateString" :"$call_time"} } }, start_hour]},
                            {"$gte": [{ "$minute":  { "$dateFromString": { "dateString" :"$call_time"} } }, start_minute]}
                        ]
                    }
                ]
            })


        if "$lt" in time_condition:
            end_hour = int(time_condition["$lt"].split(':')[0])
            end_minute =int(time_condition["$lt"].split(':')[1])
            expr_conditions.append({
                "$or": [{ "$lt": [ { "$hour": { "$dateFromString": { "dateString" :"$call_time"} }}, end_hour]},
                    {
                        "$and": [
                            { "$eq": [{ "$hour": { "$dateFromString": { "dateString" :"$call_time"} }}, end_hour]},
                            {"$lt": [{ "$minute":  { "$dateFromString": { "dateString" :"$call_time"} } }, end_minute]}
                        ]
                    }
                ]
            })

        # ✅ If both `$gte` and `$lt` exist, combine them in `$and`, otherwise return single condition
        if expr_conditions:
            adjusted_condition = {"$expr": {"$and": expr_conditions} if len(expr_conditions) > 1 else expr_conditions[0]}
        print("Generated MongoDB Query:", adjusted_condition)  # Debugging
  
    return adjusted_condition

def get_last_weekday(target_weekday):
    today = datetime.today()
    day = (today.weekday() + 2) % 7  
    days_ago = (day - target_weekday) % 7 or 7
    last_weekday = today - timedelta(days=days_ago)
    return last_weekday.strftime("%Y-%m-%dT00:00:00Z"), last_weekday.strftime("%Y-%m-%dT23:59:59Z")

# MongoDB query mapping function
def convert_to_mongo(query):
    """
    Convert natural language queries to MongoDB queries.
    (This is a simplified example, you should improve it)
    """
    mongo_query = {}
    is_count_query = any(word in query.lower() for word in COUNT_WORDS)
    query=normalize_query(query)
    agent = extract_agents(query)
    customer = extract_customers(query)
    call_status = extract_call_status(query)
    duration = extract_duration(query)
    start_date, end_date = get_date_range(query)
    print(start_date, end_date)
    time_condition = extract_time_range(query)
    query_words = query.lower().split()
    requested_weekday = None

    for day in WEEKDAYS.keys():
        print(day)
        if day in query:
            requested_weekday = day
            break

    # If agent is mentioned
    if agent:
        mongo_query["agent"] = agent

    # If customer is mentioned
    if customer:
        mongo_query["customer"] = customer

    # If call status is mentioned
    if call_status:
        mongo_query["call_status"] = call_status

    # If date range is provided
    if start_date and end_date:
        mongo_query["call_time"] = {"$gte": start_date, "$lt": end_date}
    
   
    # If duration is mentioned
    if duration:
        mongo_query["duration_minutes"] = {"$gt": duration}
    print(start_date, end_date)
    print(time_condition)
    
    
    if requested_weekday:
        weekday_num = WEEKDAYS[requested_weekday]  # Convert weekday name to number

        if any(day in query.lower() for day in ["last monday", "last tuesday", "last wednesday", 
                                                "last thursday", "last friday", "last saturday", "last sunday"]):
            # Case 1: Query asks for "last Monday", "last Tuesday", etc.
            start_date, end_date = get_last_weekday(weekday_num)
            mongo_query["call_time"] = {"$gte": start_date, "$lt": end_date}

        else:
            # Case 2: Query asks for just "Monday", "Tuesday", etc.
            mongo_query["$expr"] = { "$eq": [{ "$dayOfWeek": { "$dateFromString": { "dateString" :"$call_time"} } }, weekday_num] }

    if time_condition:
        adjusted_time_condition = adjust_time_condition(time_condition, start_date, end_date)
        if adjusted_time_condition:
            if start_date is not None and end_date is not None:
                if "call_time" in mongo_query:
                # Combine time condition with existing date/weekday condition
                    mongo_query["call_time"] = { "$and": [mongo_query["call_time"], adjusted_time_condition] }
                else:
                # Apply time condition alone if no date filtering is used   
                    mongo_query['call_time']=adjusted_time_condition
            else:
                if "call_time" in mongo_query:
                    mongo_query["call_time"] = { "$and": [mongo_query["call_time"], adjusted_time_condition] }
                elif "$expr" in mongo_query:
                    mongo_query["$expr"] = { "$and": [mongo_query["$expr"], adjusted_time_condition] }
                else:
                    mongo_query["$expr"] = adjusted_time_condition

   
            
    if "average" in query and  "duration" in query:
        match_stage = {"$match": mongo_query} if mongo_query else {"$match": {}}
        group_by_fields={}

        if "call status" in query or call_status:
            group_by_fields["call_status"]= "$call_status"
        if "agent" in query :
            group_by_fields["agent"] = "$agent"
        if agent:
            group_by_fields["agent"]="$agent"
        if "customer" in query  or "customers" in query or customer:
            group_by_fields["customer"] = "$customer"
        
        group_id = group_by_fields if group_by_fields else None
        print("group id", group_id)
        pipeline = [
            match_stage,  # Match the base filters
            {"$group": {
                "_id": group_id, 
                "avg_duration": {"$avg": "$duration_minutes"}
            }}
        ]
        return pipeline

    if is_count_query:
        pipeline = [
            {"$match": mongo_query},
            {"$count": "total_calls"}
        ]
        return pipeline
    
    if "longest duration" in query or "longest call duration" in query:
        pipeline = [
            {"$match": mongo_query},
            {"$sort": {"duration_minutes": -1}},
            {"$limit": 1}
        ]
        return pipeline


    if "frequent" in query:
        # Identify the status if any (completed, missed, etc.)
        if call_status:
            pipeline = [
                {"$match": mongo_query},  # Apply the base filters
                {"$group": {
                    "_id": "$agent",  # Group by agent
                    "call_count": {"$sum": 1},  # Count the number of calls per agent
                    "call_status": {"$first": "$call_status"}  # Track the call status
                }},
                {"$match": {"call_status": call_status}},  # Filter by call status
                {"$sort": {"call_count": -1}},  # Sort by call count (descending)
                {"$limit": 1}  # Get the top agent with most calls for the given status
            ]
            return pipeline
        
        if "top" in query:
            pipeline = [
                {"$match": mongo_query},
                {"$group": {"_id": "$agent", "call_count": {"$sum": 1}}},
                {"$sort": {"call_count": -1}},
                {"$limit": 5}
            ]
            return pipeline
    
        # If no specific status is mentioned, find the agent with the most total calls
        pipeline = [
            {"$match": mongo_query},  # Apply the base filters
            {"$group": {
                "_id": "$agent",  # Group by agent
                "call_count": {"$sum": 1}  # Count the number of calls per agent
            }},
            {"$sort": {"call_count": -1}},  # Sort by call count (descending)
            {"$limit": 1}  # Get the top agent with most calls
        ]
        return pipeline

    if not is_count_query and not "average duration" in query:
        return {"find": mongo_query}  # Use find query if it's a simple query

    
    return mongo_query


def generate_mongo_query(query):
    mongo_query = convert_to_mongo(query)
    print("before json dumps mongo:", mongo_query)
    # Convert Python object to a properly formatted JSON string
    return json.dumps(mongo_query)  

'''queries = [
    "who has the most frequent completed calls?",
    "total calls in last month",
    "how many missed calls in last week?",
    "average duration of calls",
    "most frequent calls"
]

for q in queries:
    mongo_q = generate_mongo_query(q)
    print(f"\nQuery: {q}")
    print(f"MongoDB Query: {mongo_q}")
'''

