import time
from pymongo import MongoClient
from datetime import datetime, timedelta
import pyotp
from SmartApi.smartConnect import SmartConnect
from fastapi import HTTPException
import concurrent.futures
from datetime import datetime, timedelta
import pytz
# MongoDB connection
mongo_uri = "mongodb+srv://SupremeRahul:***REDACTED***@clusternse.wpf8cel.mongodb.net/"
client = MongoClient(mongo_uri)
db = client['SmartAPI']

portfolio_collection = db['Angelone Overall Portfolio Track']
stocks_collection = db['Angelone Stocks Portfolio Track']
credentials_collection = db['Angelone Portfolio Tracking User Credentials']


# Function to generate the TOTP for 2FA
def generate_totp(totp_secret):
    return pyotp.TOTP(totp_secret).now()


# Login and fetch portfolio data
def login_and_fetch_portfolio(apiKey, username, password, totp_secret):
    obj = SmartConnect(api_key=apiKey)
    try:
        print("Logging in and fetching portfolio data...")
        data = obj.generateSession(username, password,
                                   generate_totp(totp_secret))
        refreshToken = data['data']['refreshToken']
        NameOfUser = obj.getProfile(refreshToken)['data']['name']
        client_code = obj.getProfile(refreshToken)['data']['clientcode']
        user_name = ' '.join(NameOfUser.split())
        print(
            f"Successfully logged in as {user_name} with client code {client_code}"
        )
        return obj, refreshToken, user_name, client_code
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Error during login: {e}")


# Define the Indian time zone (IST)
IST = pytz.timezone('Asia/Kolkata')

# Simulated list of NSE trading holidays fetched from https://www.nseindia.com/resources/exchange-communication-holidays
TRADING_HOLIDAYS = [
    "2024-03-29",  # Example: Holi
    "2024-08-15",  # Independence Day
    "2024-10-02",  # Gandhi Jayanti
    # Add more holidays as needed...
]


def is_trading_holiday(date):
    """Check if the given date is a trading holiday."""
    return date.strftime("%Y-%m-%d") in TRADING_HOLIDAYS


def find_previous_working_day(date):
    """Find the most recent working day by recursively skipping trading holidays and weekends."""
    while date.weekday() in [
            5, 6
    ] or is_trading_holiday(date):  # Skip Saturday=5, Sunday=6, and holidays
        date -= timedelta(days=1)
    return date


def fetch_dates():
    print("Fetching dates for historical OHLC data...")

    # Get the current time in IST
    now = datetime.now(IST)
    day_of_week = now.weekday()  # Monday is 0, Sunday is 6
    fixed_time_1 = "09:15"
    fixed_time_2 = "15:30"

    # Step 1: Check if today is a trading holiday or the weekend
    if is_trading_holiday(now) or day_of_week in [
            5, 6
    ]:  # Trading holiday or weekend (Saturday/Sunday)
        previous_day = find_previous_working_day(
            now - timedelta(days=1))  # Find last working day
        print(
            f"Today is a non-working day. Previous working day: {previous_day.strftime('%Y-%m-%d')}"
        )

        # Fetch the last two valid trading days
        from_date = find_previous_working_day(previous_day - timedelta(days=1))
        to_date = previous_day

    # Step 2: If today is not a holiday or weekend, follow the time-based logic properly
    else:
        # Case 1: Monday before 9:15 AM -> Treat Monday as Friday
        if day_of_week == 0 and now.time() < datetime.strptime(
                "09:15", "%H:%M").time():
            from_date = find_previous_working_day(
                now - timedelta(days=4))  # Wednesday
            to_date = find_previous_working_day(now -
                                                timedelta(days=3))  # Thursday

        # Case 2: Monday after 9:15 AM -> Fetch Thursday and Friday
        elif day_of_week == 0 and now.time() >= datetime.strptime(
                "09:15", "%H:%M").time():
            from_date = find_previous_working_day(
                now - timedelta(days=4))  # Thursday
            to_date = find_previous_working_day(now -
                                                timedelta(days=3))  # Friday

        # Case 3: Tuesday before 9:15 AM -> Treat Tuesday as Monday
        elif day_of_week == 1 and now.time() < datetime.strptime(
                "09:15", "%H:%M").time():
            from_date = find_previous_working_day(
                now - timedelta(days=4))  # Thursday
            to_date = find_previous_working_day(now -
                                                timedelta(days=3))  # Friday

        # Case 4: Tuesday after 9:15 AM -> Fetch Friday and Monday
        elif day_of_week == 1 and now.time() >= datetime.strptime(
                "09:15", "%H:%M").time():
            from_date = find_previous_working_day(now -
                                                  timedelta(days=3))  # Friday
            to_date = find_previous_working_day(now -
                                                timedelta(days=1))  # Monday

        # Case 5: Wednesday before 9:15 AM -> Treat Wednesday as Tuesday
        elif day_of_week == 2 and now.time() < datetime.strptime(
                "09:15", "%H:%M").time():
            from_date = find_previous_working_day(now -
                                                  timedelta(days=3))  # Friday
            to_date = find_previous_working_day(now -
                                                timedelta(days=1))  # Monday

        # Case 6: Wednesday after 9:15 AM -> Fetch Monday and Tuesday
        elif day_of_week == 2 and now.time() >= datetime.strptime(
                "09:15", "%H:%M").time():
            from_date = find_previous_working_day(now -
                                                  timedelta(days=2))  # Monday
            to_date = find_previous_working_day(now -
                                                timedelta(days=1))  # Tuesday

        # Case 7: Thursday before 9:15 AM -> Treat Thursday as Wednesday
        elif day_of_week == 3 and now.time() < datetime.strptime(
                "09:15", "%H:%M").time():
            from_date = find_previous_working_day(now -
                                                  timedelta(days=2))  # Monday
            to_date = find_previous_working_day(now -
                                                timedelta(days=1))  # Tuesday

        # Case 8: Thursday after 9:15 AM -> Fetch Tuesday and Wednesday
        elif day_of_week == 3 and now.time() >= datetime.strptime(
                "09:15", "%H:%M").time():
            from_date = find_previous_working_day(now -
                                                  timedelta(days=2))  # Tuesday
            to_date = find_previous_working_day(now -
                                                timedelta(days=1))  # Wednesday

        # Case 9: Friday before 9:15 AM -> Treat Friday as Thursday
        elif day_of_week == 4 and now.time() < datetime.strptime(
                "09:15", "%H:%M").time():
            from_date = find_previous_working_day(now -
                                                  timedelta(days=2))  # Tuesday
            to_date = find_previous_working_day(now -
                                                timedelta(days=1))  # Wednesday

        # Case 10: Friday after 9:15 AM -> Fetch Wednesday and Thursday
        elif day_of_week == 4 and now.time() >= datetime.strptime(
                "09:15", "%H:%M").time():
            from_date = find_previous_working_day(
                now - timedelta(days=2))  # Wednesday
            to_date = find_previous_working_day(now -
                                                timedelta(days=1))  # Thursday

    # Step 3: Apply time logic (market open and close times)
    from_date_str = from_date.strftime("%Y-%m-%d ") + fixed_time_1
    to_date_str = to_date.strftime("%Y-%m-%d ") + fixed_time_2

    print(f"From date: {from_date_str}, To date: {to_date_str}")
    return [from_date_str, to_date_str]


# Fetch historical OHLC data with rate limiting and detailed logging
def fetch_historical_ohlc(obj, symbol, token):
    try:
        print(f"Fetching OHLC data for {symbol}...")
        # Fetch dates specifically for OHLC
        from_date, to_date = fetch_dates(
        )  # Use the updated function for dates
        time.sleep(0.5)  # Slow down request to avoid rate-limit issues
        historical_params = {
            "exchange": "NSE",
            "symboltoken": token,
            "interval": "ONE_DAY",
            "fromdate": from_date,
            "todate": to_date
        }
        response = obj.getCandleData(historical_params)
        if 'data' in response and len(response['data']) > 0:
            print(f"Previous close for {symbol}: {response['data'][0][4]}")
            return response['data'][0][4]  # Return the closing price
        else:
            raise ValueError(f"No historical data found for {symbol}")
    except Exception as e:
        print(f"Error fetching OHLC data for {symbol}: {e}")
        return {"error": str(e)}


# Backoff mechanism for handling API rate-limit errors
def fetch_with_backoff(api_call, retries=5, backoff_factor=1):
    for i in range(retries):
        try:
            return api_call()
        except Exception as e:
            if "Access denied because of exceeding access rate" in str(e):
                wait_time = backoff_factor * (2**i)  # Exponential backoff
                print(
                    f"Rate limit exceeded. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                raise e
    raise Exception("Failed after maximum retries")


# Function to fetch the trade book
def fetch_trade_book(obj):
    trade_book = obj.tradeBook()
    if trade_book['status'] and 'data' in trade_book:
        return trade_book['data']
    else:
        return []  # Return an empty list if there are no trades


# Function to check if the stock was bought today
def is_stock_bought_today(stock, trades):
    # Check if the stock is in today's trade book with a 'BUY' transaction
    if not trades:  # Handle case where trade book is empty
        return False, None, 0

    for trade in trades:
        if trade['tradingsymbol'] == stock['tradingsymbol'] and trade[
                'transactiontype'] == 'BUY':
            return True, float(trade['fillprice']), int(trade['fillsize'])
    return False, None, 0


# Update portfolio data with logic to check for duplicates and update instead of appending
def update_portfolio_data(obj, user_name, client_code):
    today_date = datetime.today().strftime('%d-%m-%Y')

    def fetch_holdings():
        return obj.allholding()

    try:
        print(
            f"Fetching user holdings for {user_name} with client code {client_code}..."
        )
        allholding_data = fetch_with_backoff(fetch_holdings)
        holdings_data = allholding_data['data']['holdings']
        total_portfolio_data = allholding_data['data']['totalholding']
        print(f"Holdings fetched: {len(holdings_data)} stocks for {user_name}")

        # Fetch the trade book to cross-reference today's trades
        trade_book = fetch_trade_book(obj)
    except Exception as e:
        print(f"Error fetching holdings data for {user_name}: {e}")
        return

    total_today_gain = 0

    # Step 1: Check if the ClientCode already exists
    client_entry = stocks_collection.find_one({"ClientCode": client_code})

    if client_entry:
        print(f"Client {client_code} found in the database.")
    else:
        print(
            f"Client {client_code} not found, creating new entry for the client."
        )

    for stock in holdings_data:
        print(f"Processing stock: {stock['tradingsymbol']}")

        # Calculate today's gain
        bought_today, today_fillprice, today_fillsize = is_stock_bought_today(
            stock, trade_book)

        if bought_today:
            today_gain = (stock['ltp'] - today_fillprice) * today_fillsize
            old_quantity = stock['quantity'] - today_fillsize
            if old_quantity > 0:
                old_holdings_gain = (stock['ltp'] -
                                     stock['close']) * old_quantity
                today_gain += old_holdings_gain
            print(
                f"Stock {stock['tradingsymbol']} was bought today. Calculated today_gain: {today_gain}"
            )
        else:
            today_gain = (stock['ltp'] - stock['close']) * stock['quantity']
            print(
                f"Stock {stock['tradingsymbol']} was held from previous days. Calculated today_gain: {today_gain}"
            )

        total_today_gain += today_gain

        # Step 2: Always add or update today's entry for each stock
        print(
            f"Ensuring stock {stock['tradingsymbol']} has entry for {today_date}"
        )
        try:
            stocks_collection.update_one(
                {
                    "ClientCode": client_code,
                    "PortfolioStocks.stockName": stock['tradingsymbol']
                },
                {
                    "$addToSet": {
                        "PortfolioStocks.$.entries": {
                            "date": today_date,
                            "exchange": stock['exchange'],
                            "quantity": stock['quantity'],
                            "realisedquantity": stock['realisedquantity'],
                            "authorisedquantity": stock['authorisedquantity'],
                            "product": stock['product'],
                            "averageprice": stock['averageprice'],
                            "symboltoken": stock['symboltoken'],
                            "overallPnL": stock['profitandloss'],
                            "pnlpercentage": stock['pnlpercentage'],
                            "todayGain": round(today_gain, 2)
                        }
                    }
                },
                upsert=
                True  # Ensure the stock entry is added if it doesn't exist
            )
            print(
                f"Successfully added or updated stock {stock['tradingsymbol']} for {today_date}"
            )
        except Exception as e:
            print(
                f"Error adding or updating stock {stock['tradingsymbol']} for {today_date}: {e}"
            )

    print(f"Total portfolio gain today for {user_name}: {total_today_gain}")

    # Update total portfolio as before
    portfolio_entry = portfolio_collection.find_one({
        "ClientCode":
        client_code,
        "Portfolio.date":
        today_date
    })

    if portfolio_entry:
        try:
            portfolio_collection.update_one(
                {
                    "ClientCode": client_code,
                    "Portfolio.date": today_date
                }, {
                    "$set": {
                        "Portfolio.$[elem].totalholdingvalue":
                        round(total_portfolio_data['totalholdingvalue'], 2),
                        "Portfolio.$[elem].totalinvvalue":
                        round(total_portfolio_data['totalinvvalue'], 2),
                        "Portfolio.$[elem].totalprofitandloss":
                        round(total_portfolio_data['totalprofitandloss'], 2),
                        "Portfolio.$[elem].totalpnlpercentage":
                        total_portfolio_data['totalpnlpercentage'],
                        "Portfolio.$[elem].totalTodayGain":
                        round(total_today_gain, 2)
                    }
                },
                array_filters=[{
                    "elem.date": today_date
                }])
            print(f"Successfully updated total portfolio for {today_date}.")
        except Exception as e:
            print(f"Error updating total portfolio for {today_date}: {e}")
    else:
        try:
            portfolio_collection.update_one({"ClientCode": client_code}, {
                "$push": {
                    "Portfolio": {
                        "date":
                        today_date,
                        "totalholdingvalue":
                        round(total_portfolio_data['totalholdingvalue'], 2),
                        "totalinvvalue":
                        round(total_portfolio_data['totalinvvalue'], 2),
                        "totalprofitandloss":
                        round(total_portfolio_data['totalprofitandloss'], 2),
                        "totalpnlpercentage":
                        total_portfolio_data['totalpnlpercentage'],
                        "totalTodayGain":
                        round(total_today_gain, 2)
                    }
                }
            },
                                            upsert=True)
            print(
                f"Successfully added new total portfolio entry for {today_date}."
            )
        except Exception as e:
            print(
                f"Error adding new total portfolio entry for {today_date}: {e}"
            )

    return "Portfolio updated successfully!"


# Function to handle each user's portfolio update in a separate thread
def process_user_portfolio(user):
    apiKey = user['apiKey'][0]  # Use only the first API key
    username = user['clientId']
    password = user['password']
    totp_secret = user['totp_secret']

    try:
        # Login and fetch data for each user
        obj, refreshToken, user_name, client_code = login_and_fetch_portfolio(
            apiKey, username, password, totp_secret)
        result = update_portfolio_data(obj, user_name, client_code)
        print(result)
    except Exception as e:
        print(f"Error processing portfolio for {user['clientName']}: {e}")


if __name__ == "__main__":
    a = time.time()
    try:
        print("Starting the portfolio update process for all users...")

        # Fetch all user credentials
        all_users = credentials_collection.find()

        # Use ThreadPoolExecutor for multi-threading
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(process_user_portfolio, user)
                for user in all_users
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    future.result()  # Ensure any raised exceptions are caught
                except Exception as e:
                    print(f"Error: {e}")

    except Exception as e:
        print(f"An error occurred while iterating through users: {e}")
    b = time.time()

    print(f"Total Execution time {b-a} seconds")

# This is 100% working code! as on testing on 16/09/2024 at 12:54 AM! Clone Doc issues also fixed
