import time
from pymongo import MongoClient, ASCENDING
from datetime import datetime, timedelta
import pyotp
from SmartApi.smartConnect import SmartConnect
from fastapi import HTTPException
import concurrent.futures
import pytz
import uuid  # For unique run identifiers
import logging  # Import logging module

# Suppress INFO and DEBUG logs from smartConnect
logging.getLogger('smartConnect').setLevel(logging.WARNING)

# MongoDB connection
mongo_uri = "mongodb+srv://SupremeRahul:***REDACTED***@clusternse.wpf8cel.mongodb.net/"
client = MongoClient(mongo_uri)
db = client['SmartAPI']

# Backup DB connection
backup_db = client['SmartAPI-Backup']

# Collections in main DB
portfolio_collection = db['Angelone Overall Portfolio Track']
stocks_collection = db['Angelone Stocks Portfolio Track']
credentials_collection = db['Angelone Portfolio Tracking User Credentials']
main_logs_collection = db['PortfolioLogs']

# Collections in backup DB
backup_portfolio_collection = backup_db['Angelone Overall Portfolio Track']
backup_stocks_collection = backup_db['Angelone Stocks Portfolio Track']
backup_credentials_collection = backup_db['Angelone Portfolio Tracking User Credentials']
backup_logs_collection = backup_db['PortfolioLogs']

# Ensure unique index on ClientCode in PortfolioLogs to prevent duplicates
main_logs_collection.create_index([("ClientCode", ASCENDING)], unique=True)
backup_logs_collection.create_index([("ClientCode", ASCENDING)], unique=True)

# Function to generate the TOTP for 2FA
def generate_totp(totp_secret):
    return pyotp.TOTP(totp_secret).now()

# PortfolioLogger Class for handling logs
class PortfolioLogger:
    def __init__(self, logs_collection, backup_logs_collection, client_code, date):
        self.logs_collection = logs_collection
        self.backup_logs_collection = backup_logs_collection
        self.client_code = client_code
        self.date = date
        self.run_version = self.get_next_run_version()

    def get_next_run_version(self):
        # Fetch existing run versions for the client and date
        client_log = self.logs_collection.find_one({"ClientCode": self.client_code})
        if not client_log or "logs" not in client_log or self.date not in client_log["logs"]:
            return "v1"
        existing_versions = [
            key for key in client_log["logs"][self.date].keys() if key.startswith("v")
        ]
        if not existing_versions:
            return "v1"
        numbers = [int(v[1:]) for v in existing_versions if v[1:].isdigit()]
        if not numbers:
            return "v1"
        max_v = max(numbers)
        return f"v{max_v + 1}"

    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_message_db = f"{timestamp}: {message}"
        log_path = f"logs.{self.date}.{self.run_version}"

        # Update main logs_collection
        self.logs_collection.update_one(
            {"ClientCode": self.client_code},
            {"$setOnInsert": {"ClientCode": self.client_code, "logs": {}}},
            upsert=True
        )

        # Initialize the run version if it doesn't exist
        self.logs_collection.update_one(
            {"ClientCode": self.client_code},
            {"$setOnInsert": {log_path: []}},
            upsert=True
        )

        # Append the log message to main DB
        self.logs_collection.update_one(
            {"ClientCode": self.client_code},
            {"$push": {log_path: full_message_db}}
        )

        # Update backup_logs_collection
        self.backup_logs_collection.update_one(
            {"ClientCode": self.client_code},
            {"$setOnInsert": {"ClientCode": self.client_code, "logs": {}}},
            upsert=True
        )

        # Initialize the run version in backup DB if it doesn't exist
        self.backup_logs_collection.update_one(
            {"ClientCode": self.client_code},
            {"$setOnInsert": {log_path: []}},
            upsert=True
        )

        # Append the log message to backup DB
        self.backup_logs_collection.update_one(
            {"ClientCode": self.client_code},
            {"$push": {log_path: full_message_db}}
        )

        # Prepare the print message with ClientCode
        full_message_print = f"[{timestamp} {self.client_code}] : {message}"

        # Print the log message to the console
        print(full_message_print)

# Login and fetch portfolio data
def login_and_fetch_portfolio(apiKey, username, password, totp_secret, logger=None):
    obj = SmartConnect(api_key=apiKey)
    try:
        if logger:
            logger.log("Attempting to log in and fetch portfolio data...")
        else:
            print("Logging in and fetching portfolio data...")
        data = obj.generateSession(username, password, generate_totp(totp_secret))
        refreshToken = data['data']['refreshToken']
        NameOfUser = obj.getProfile(refreshToken)['data']['name']
        client_code = obj.getProfile(refreshToken)['data']['clientcode']
        user_name = ' '.join(NameOfUser.split())
        if logger:
            logger.log(f"Successfully logged in as {user_name} with client code {client_code}")
        else:
            print(f"Successfully logged in as {user_name} with client code {client_code}")
        return obj, refreshToken, user_name, client_code
    except Exception as e:
        error_message = f"Error during login: {e}"
        if logger:
            logger.log(error_message)
        raise HTTPException(status_code=401, detail=error_message)

# Define the Indian time zone (IST)
IST = pytz.timezone('Asia/Kolkata')

# Simulated list of NSE trading holidays
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
    while date.weekday() in [5, 6] or is_trading_holiday(date):  # Skip Saturday=5, Sunday=6, and holidays
        date -= timedelta(days=1)
    return date

def fetch_dates(logger):
    logger.log("Fetching dates for historical OHLC data...")

    # Get the current time in IST
    now = datetime.now(IST)
    day_of_week = now.weekday()  # Monday is 0, Sunday is 6
    fixed_time_1 = "09:15"
    fixed_time_2 = "15:30"

    # Step 1: Check if today is a trading holiday or the weekend
    if is_trading_holiday(now) or day_of_week in [5, 6]:  # Trading holiday or weekend (Saturday/Sunday)
        previous_day = find_previous_working_day(now - timedelta(days=1))  # Find last working day
        logger.log(f"Today is a non-working day. Previous working day: {previous_day.strftime('%Y-%m-%d')}")

        # Fetch the last two valid trading days
        from_date = find_previous_working_day(previous_day - timedelta(days=1))
        to_date = previous_day

    # Step 2: If today is not a holiday or weekend, follow the time-based logic properly
    else:
        # Define all cases
        if day_of_week == 0 and now.time() < datetime.strptime("09:15", "%H:%M").time():
            from_date = find_previous_working_day(now - timedelta(days=4))  # Wednesday
            to_date = find_previous_working_day(now - timedelta(days=3))  # Thursday

        elif day_of_week == 0 and now.time() >= datetime.strptime("09:15", "%H:%M").time():
            from_date = find_previous_working_day(now - timedelta(days=4))  # Thursday
            to_date = find_previous_working_day(now - timedelta(days=3))  # Friday

        elif day_of_week == 1 and now.time() < datetime.strptime("09:15", "%H:%M").time():
            from_date = find_previous_working_day(now - timedelta(days=4))  # Thursday
            to_date = find_previous_working_day(now - timedelta(days=3))  # Friday

        elif day_of_week == 1 and now.time() >= datetime.strptime("09:15", "%H:%M").time():
            from_date = find_previous_working_day(now - timedelta(days=3))  # Friday
            to_date = find_previous_working_day(now - timedelta(days=1))  # Monday

        elif day_of_week == 2 and now.time() < datetime.strptime("09:15", "%H:%M").time():
            from_date = find_previous_working_day(now - timedelta(days=3))  # Friday
            to_date = find_previous_working_day(now - timedelta(days=1))  # Monday

        elif day_of_week == 2 and now.time() >= datetime.strptime("09:15", "%H:%M").time():
            from_date = find_previous_working_day(now - timedelta(days=2))  # Monday
            to_date = find_previous_working_day(now - timedelta(days=1))  # Tuesday

        elif day_of_week == 3 and now.time() < datetime.strptime("09:15", "%H:%M").time():
            from_date = find_previous_working_day(now - timedelta(days=2))  # Monday
            to_date = find_previous_working_day(now - timedelta(days=1))  # Tuesday

        elif day_of_week == 3 and now.time() >= datetime.strptime("09:15", "%H:%M").time():
            from_date = find_previous_working_day(now - timedelta(days=2))  # Tuesday
            to_date = find_previous_working_day(now - timedelta(days=1))  # Wednesday

        elif day_of_week == 4 and now.time() < datetime.strptime("09:15", "%H:%M").time():
            from_date = find_previous_working_day(now - timedelta(days=2))  # Tuesday
            to_date = find_previous_working_day(now - timedelta(days=1))  # Wednesday

        elif day_of_week == 4 and now.time() >= datetime.strptime("09:15", "%H:%M").time():
            from_date = find_previous_working_day(now - timedelta(days=2))  # Wednesday
            to_date = find_previous_working_day(now - timedelta(days=1))  # Thursday

        else:
            # Default case, shouldn't occur
            from_date = find_previous_working_day(now - timedelta(days=1))
            to_date = now

        logger.log(f"Determined trading dates: From {from_date.strftime('%Y-%m-%d')} To {to_date.strftime('%Y-%m-%d')}")

    # Step 3: Apply time logic (market open and close times)
    from_date_str = from_date.strftime("%Y-%m-%d ") + fixed_time_1
    to_date_str = to_date.strftime("%Y-%m-%d ") + fixed_time_2

    logger.log(f"From date: {from_date_str}, To date: {to_date_str}")
    return [from_date_str, to_date_str]

# Fetch historical OHLC data with rate limiting and detailed logging
def fetch_historical_ohlc(obj, symbol, token, logger):
    try:
        logger.log(f"Fetching OHLC data for {symbol}...")
        # Fetch dates specifically for OHLC
        from_date, to_date = fetch_dates(logger)
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
            logger.log(f"Previous close for {symbol}: {response['data'][0][4]}")
            return response['data'][0][4]  # Return the closing price
        else:
            raise ValueError(f"No historical data found for {symbol}")
    except Exception as e:
        logger.log(f"Error fetching OHLC data for {symbol}: {e}")
        return {"error": str(e)}

# Backoff mechanism for handling API rate-limit errors
def fetch_with_backoff(api_call, logger, retries=5, backoff_factor=1):
    for i in range(retries):
        try:
            return api_call()
        except Exception as e:
            if "Access denied because of exceeding access rate" in str(e):
                wait_time = backoff_factor * (2**i)  # Exponential backoff
                logger.log(f"Rate limit exceeded. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.log(f"Error during API call: {e}")
                raise e
    error_message = "Failed after maximum retries"
    logger.log(error_message)
    raise Exception(error_message)

# Function to fetch the trade book
def fetch_trade_book(obj, logger):
    try:
        logger.log("Fetching trade book...")
        trade_book = obj.tradeBook()
        if trade_book['status'] and 'data' in trade_book:
            logger.log("Trade book fetched successfully.")
            return trade_book['data']
        else:
            logger.log("No trades found in trade book.")
            return []  # Return an empty list if there are no trades
    except Exception as e:
        logger.log(f"Error fetching trade book: {e}")
        return []

# Function to check if the stock was bought today
def is_stock_bought_today(stock, trades, logger):
    # Check if the stock is in today's trade book with a 'BUY' transaction
    if not trades:  # Handle case where trade book is empty
        return False, None, 0

    for trade in trades:
        if trade['tradingsymbol'] == stock['tradingsymbol'] and trade['transactiontype'] == 'BUY':
            logger.log(f"Stock {stock['tradingsymbol']} was bought today at price {trade['fillprice']} with size {trade['fillsize']}.")
            return True, float(trade['fillprice']), int(trade['fillsize'])
    logger.log(f"Stock {stock['tradingsymbol']} was not bought today.")
    return False, None, 0

# Update portfolio data with logic to check for duplicates and update instead of appending
def update_portfolio_data(obj, user_name, client_code, logger):
    today_date = datetime.now(IST).strftime('%d-%m-%Y')

    def fetch_holdings():
        return obj.allholding()

    try:
        logger.log(f"Fetching user holdings for {user_name} with client code {client_code}...")
        allholding_data = fetch_with_backoff(fetch_holdings, logger)
        holdings_data = allholding_data['data']['holdings']
        total_portfolio_data = allholding_data['data']['totalholding']
        logger.log(f"Holdings fetched: {len(holdings_data)} stocks for {user_name}")

        # Fetch the trade book to cross-reference today's trades
        trade_book = fetch_trade_book(obj, logger)
    except Exception as e:
        logger.log(f"Error fetching holdings data for {user_name}: {e}")
        return

    total_today_gain = 0

    # Step 1: Check if the ClientCode already exists
    client_entry = stocks_collection.find_one({"ClientCode": client_code})

    if client_entry:
        logger.log(f"Client {client_code} found in the database.")
    else:
        logger.log(f"Client {client_code} not found, creating new entry for the client.")
        # Initialize the client entry if it doesn't exist
        stocks_collection.insert_one({
            "ClientCode": client_code,
            "PortfolioStocks": []
        })
        # Also insert into backup DB
        backup_stocks_collection.insert_one({
            "ClientCode": client_code,
            "PortfolioStocks": []
        })

    for stock in holdings_data:
        logger.log(f"Processing stock: {stock['tradingsymbol']}")

        # Calculate today's gain
        bought_today, today_fillprice, today_fillsize = is_stock_bought_today(stock, trade_book, logger)

        if bought_today:
            today_gain = (stock['ltp'] - today_fillprice) * today_fillsize
            old_quantity = stock['quantity'] - today_fillsize
            if old_quantity > 0:
                old_holdings_gain = (stock['ltp'] - stock['close']) * old_quantity
                today_gain += old_holdings_gain
            logger.log(f"Stock {stock['tradingsymbol']} was bought today. Calculated today_gain: {today_gain}")
        else:
            today_gain = (stock['ltp'] - stock['close']) * stock['quantity']
            logger.log(f"Stock {stock['tradingsymbol']} was held from previous days. Calculated today_gain: {today_gain}")

        total_today_gain += today_gain

        # Step 2: Check if the stock exists in PortfolioStocks
        stock_exists = stocks_collection.find_one({
            "ClientCode": client_code,
            "PortfolioStocks.stockName": stock['tradingsymbol']
        })

        if stock_exists:
            # Step 2a: Try to update an existing entry for today's date
            update_result = stocks_collection.update_one(
                {
                    "ClientCode": client_code,
                    "PortfolioStocks.stockName": stock['tradingsymbol'],
                    "PortfolioStocks.entries.date": today_date
                },
                {
                    "$set": {
                        "PortfolioStocks.$.entries.$[entry].exchange": stock['exchange'],
                        "PortfolioStocks.$.entries.$[entry].quantity": stock['quantity'],
                        "PortfolioStocks.$.entries.$[entry].realisedquantity": stock['realisedquantity'],
                        "PortfolioStocks.$.entries.$[entry].authorisedquantity": stock['authorisedquantity'],
                        "PortfolioStocks.$.entries.$[entry].product": stock['product'],
                        "PortfolioStocks.$.entries.$[entry].averageprice": stock['averageprice'],
                        "PortfolioStocks.$.entries.$[entry].symboltoken": stock['symboltoken'],
                        "PortfolioStocks.$.entries.$[entry].overallPnL": stock['profitandloss'],
                        "PortfolioStocks.$.entries.$[entry].pnlpercentage": stock['pnlpercentage'],
                        "PortfolioStocks.$.entries.$[entry].todayGain": round(today_gain, 2)
                    }
                },
                array_filters=[{"entry.date": today_date}]
            )

            if update_result.modified_count > 0:
                logger.log(f"Successfully updated existing entry for {stock['tradingsymbol']} on {today_date}")
                # Also update in backup DB
                backup_stocks_collection.update_one(
                    {
                        "ClientCode": client_code,
                        "PortfolioStocks.stockName": stock['tradingsymbol'],
                        "PortfolioStocks.entries.date": today_date
                    },
                    {
                        "$set": {
                            "PortfolioStocks.$.entries.$[entry].exchange": stock['exchange'],
                            "PortfolioStocks.$.entries.$[entry].quantity": stock['quantity'],
                            "PortfolioStocks.$.entries.$[entry].realisedquantity": stock['realisedquantity'],
                            "PortfolioStocks.$.entries.$[entry].authorisedquantity": stock['authorisedquantity'],
                            "PortfolioStocks.$.entries.$[entry].product": stock['product'],
                            "PortfolioStocks.$.entries.$[entry].averageprice": stock['averageprice'],
                            "PortfolioStocks.$.entries.$[entry].symboltoken": stock['symboltoken'],
                            "PortfolioStocks.$.entries.$[entry].overallPnL": stock['profitandloss'],
                            "PortfolioStocks.$.entries.$[entry].pnlpercentage": stock['pnlpercentage'],
                            "PortfolioStocks.$.entries.$[entry].todayGain": round(today_gain, 2)
                        }
                    },
                    array_filters=[{"entry.date": today_date}]
                )
            else:
                # Step 2b: If no existing entry for today, add a new one
                stocks_collection.update_one(
                    {
                        "ClientCode": client_code,
                        "PortfolioStocks.stockName": stock['tradingsymbol']
                    },
                    {
                        "$push": {
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
                    }
                )
                logger.log(f"Successfully added new entry for {stock['tradingsymbol']} on {today_date}")
                # Also add to backup DB
                backup_stocks_collection.update_one(
                    {
                        "ClientCode": client_code,
                        "PortfolioStocks.stockName": stock['tradingsymbol']
                    },
                    {
                        "$push": {
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
                    }
                )
        else:
            # Step 3: If the stock does not exist, add it with today's entry
            try:
                stocks_collection.update_one(
                    {"ClientCode": client_code},
                    {
                        "$push": {
                            "PortfolioStocks": {
                                "stockName": stock['tradingsymbol'],
                                "entries": [{
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
                                }]
                            }
                        }
                    }
                )
                logger.log(f"Successfully added new stock {stock['tradingsymbol']} with entry for {today_date}")
                # Also add to backup DB
                backup_stocks_collection.update_one(
                    {"ClientCode": client_code},
                    {
                        "$push": {
                            "PortfolioStocks": {
                                "stockName": stock['tradingsymbol'],
                                "entries": [{
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
                                }]
                            }
                        }
                    }
                )
            except Exception as e:
                logger.log(f"Error adding new stock {stock['tradingsymbol']} for {today_date}: {e}")
                # Also log the error in backup DB
                try:
                    backup_logs_collection.update_one(
                        {"ClientCode": client_code},
                        {"$push": {f"logs.{today_date}.{logger.run_version}": f"Error adding new stock {stock['tradingsymbol']} for {today_date}: {e}"}}
                    )
                except Exception as backup_e:
                    logger.log(f"Error logging to backup DB: {backup_e}")

    logger.log(f"Total portfolio gain today for {user_name}: {total_today_gain}")

    # Update total portfolio as before
    portfolio_entry = portfolio_collection.find_one({
        "ClientCode": client_code,
        "Portfolio.date": today_date
    })

    if portfolio_entry:
        try:
            portfolio_collection.update_one(
                {
                    "ClientCode": client_code,
                    "Portfolio.date": today_date
                }, {
                    "$set": {
                        "Portfolio.$[elem].totalholdingvalue": round(total_portfolio_data['totalholdingvalue'], 2),
                        "Portfolio.$[elem].totalinvvalue": round(total_portfolio_data['totalinvvalue'], 2),
                        "Portfolio.$[elem].totalprofitandloss": round(total_portfolio_data['totalprofitandloss'], 2),
                        "Portfolio.$[elem].totalpnlpercentage": total_portfolio_data['totalpnlpercentage'],
                        "Portfolio.$[elem].totalTodayGain": round(total_today_gain, 2)
                    }
                },
                array_filters=[{"elem.date": today_date}]
            )
            logger.log(f"Successfully updated total portfolio for {today_date}.")
            # Also update in backup DB
            backup_portfolio_collection.update_one(
                {
                    "ClientCode": client_code,
                    "Portfolio.date": today_date
                }, {
                    "$set": {
                        "Portfolio.$[elem].totalholdingvalue": round(total_portfolio_data['totalholdingvalue'], 2),
                        "Portfolio.$[elem].totalinvvalue": round(total_portfolio_data['totalinvvalue'], 2),
                        "Portfolio.$[elem].totalprofitandloss": round(total_portfolio_data['totalprofitandloss'], 2),
                        "Portfolio.$[elem].totalpnlpercentage": total_portfolio_data['totalpnlpercentage'],
                        "Portfolio.$[elem].totalTodayGain": round(total_today_gain, 2)
                    }
                },
                array_filters=[{"elem.date": today_date}]
            )
        except Exception as e:
            logger.log(f"Error updating total portfolio for {today_date}: {e}")
            # Also update in backup DB
            try:
                backup_portfolio_collection.update_one(
                    {
                        "ClientCode": client_code,
                        "Portfolio.date": today_date
                    }, {
                        "$set": {
                            "Portfolio.$[elem].totalholdingvalue": round(total_portfolio_data['totalholdingvalue'], 2),
                            "Portfolio.$[elem].totalinvvalue": round(total_portfolio_data['totalinvvalue'], 2),
                            "Portfolio.$[elem].totalprofitandloss": round(total_portfolio_data['totalprofitandloss'], 2),
                            "Portfolio.$[elem].totalpnlpercentage": total_portfolio_data['totalpnlpercentage'],
                            "Portfolio.$[elem].totalTodayGain": round(total_today_gain, 2)
                        }
                    },
                    array_filters=[{"elem.date": today_date}]
                )
            except Exception as backup_e:
                logger.log(f"Error updating total portfolio in backup DB for {today_date}: {backup_e}")
    else:
        try:
            portfolio_collection.update_one({"ClientCode": client_code}, {
                "$push": {
                    "Portfolio": {
                        "date": today_date,
                        "totalholdingvalue": round(total_portfolio_data['totalholdingvalue'], 2),
                        "totalinvvalue": round(total_portfolio_data['totalinvvalue'], 2),
                        "totalprofitandloss": round(total_portfolio_data['totalprofitandloss'], 2),
                        "totalpnlpercentage": total_portfolio_data['totalpnlpercentage'],
                        "totalTodayGain": round(total_today_gain, 2)
                    }
                }
            }, upsert=True)
            logger.log(f"Successfully added new total portfolio entry for {today_date}.")
            # Also add to backup DB
            backup_portfolio_collection.update_one({"ClientCode": client_code}, {
                "$push": {
                    "Portfolio": {
                        "date": today_date,
                        "totalholdingvalue": round(total_portfolio_data['totalholdingvalue'], 2),
                        "totalinvvalue": round(total_portfolio_data['totalinvvalue'], 2),
                        "totalprofitandloss": round(total_portfolio_data['totalprofitandloss'], 2),
                        "totalpnlpercentage": total_portfolio_data['totalpnlpercentage'],
                        "totalTodayGain": round(total_today_gain, 2)
                    }
                }
            }, upsert=True)
        except Exception as e:
            logger.log(f"Error adding new total portfolio entry for {today_date}: {e}")
            # Also add to backup DB
            try:
                backup_portfolio_collection.update_one({"ClientCode": client_code}, {
                    "$push": {
                        "Portfolio": {
                            "date": today_date,
                            "totalholdingvalue": round(total_portfolio_data['totalholdingvalue'], 2),
                            "totalinvvalue": round(total_portfolio_data['totalinvvalue'], 2),
                            "totalprofitandloss": round(total_portfolio_data['totalprofitandloss'], 2),
                            "totalpnlpercentage": total_portfolio_data['totalpnlpercentage'],
                            "totalTodayGain": round(total_today_gain, 2)
                        }
                    }
                }, upsert=True)
            except Exception as backup_e:
                logger.log(f"Error adding new total portfolio entry to backup DB for {today_date}: {backup_e}")

    return "Portfolio updated successfully!"

# Function to handle each user's portfolio update in a separate thread
def process_user_portfolio(user):
    apiKey = user['apiKey'][0]  # Use only the first API key
    username = user['clientId']
    password = user['password']
    totp_secret = user['totp_secret']

    try:
        # Determine today's date in 'dd-mm-yyyy'
        today_date = datetime.now(IST).strftime('%d-%m-%Y')

        # Initialize logger for this client and run
        logger = PortfolioLogger(main_logs_collection, backup_logs_collection, user['clientId'], today_date)

        # Login and fetch data for each user with logger
        obj, refreshToken, user_name, client_code = login_and_fetch_portfolio(
            apiKey, username, password, totp_secret, logger=logger)

        # Update portfolio data with logging
        result = update_portfolio_data(obj, user_name, client_code, logger)
        logger.log(result)
    except Exception as e:
        if 'client_code' in locals() and client_code:
            try:
                logger.log(f"Error processing portfolio for {user['clientName']}: {e}")
            except:
                # In case logger was not initialized
                print(f"Error processing portfolio for {user['clientName']}: {e}")
        else:
            # Log to a general 'UNKNOWN' client or handle accordingly
            print(f"Error processing portfolio for {user['clientName']}: {e}")

if __name__ == "__main__":
    start_time = time.time()
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
    end_time = time.time()

    print(f"Total Execution time {end_time - start_time} seconds")
