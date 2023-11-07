""""
Copyright © antonionardella 2023 - https://github.com/antonionardella (https://antonionardella.it)
Description:
Get API data for Shimmer from different sources
- Bitfinex V2 API
Version: 5.5.0
"""
import requests
import logging
import helpers.configuration_manager as configuration_manager
import json
import locale
import discord
import datetime
import pickle
import traceback

logger = logging.getLogger("discord_bot")

# Load configuration
config = configuration_manager.load_config('config.json')

# Shimmer data
coingecko_coin_id = config["coingecko_coin_id"]
coingecko_exchange_id = config["coingecko_exchange_id"]
bitfinex_ticker = config["bitfinex_ticker"]
geckoterminal_ticker = config["geckoterminal_ticker"]
shimmer_onchain_deposit_alias = config["shimmer_onchain_deposit_alias"]

# API URLs
coingecko_exchange_url = f"https://api.coingecko.com/api/v3/exchanges/{coingecko_exchange_id}/tickers?coin_ids={coingecko_coin_id}"
bitfinex_book_url = f"https://api-pub.bitfinex.com/v2/book/{bitfinex_ticker}/P0"
defillama_url = "https://api.llama.fi/v2/chains"
geckoterminal_url = f"https://api.geckoterminal.com/api/v2/networks/{geckoterminal_ticker}/pools"
shimmer_explorer_api_url = f"https://api.shimmer.network/api/indexer/v1/outputs/alias/{shimmer_onchain_deposit_alias}"

# Functions

async def format_currency(value, currency_symbol="$"):
    # Split integer and decimal parts if there is a decimal point
    parts = str(value).split('.')
    integer_part = parts[0]
    decimal_part = parts[1] if len(parts) > 1 else ""

    # Determine the number of decimal places based on the value
    num_decimal_places = 2 if int(integer_part) > 0 else 5

    # Limit decimal part to the specified number of digits
    if decimal_part and len(decimal_part) > num_decimal_places:
        decimal_part = decimal_part[:num_decimal_places]

    # Format integer part with commas
    formatted_integer_part = ""
    for i in range(len(integer_part), 0, -3):
        formatted_integer_part = "," + integer_part[max(i-3, 0):i] + formatted_integer_part

    # Remove leading comma if present
    if formatted_integer_part and formatted_integer_part[0] == ",":
        formatted_integer_part = formatted_integer_part[1:]

    # Combine integer and decimal parts with appropriate separator
    formatted_value = formatted_integer_part + ("." + decimal_part if decimal_part else "")

    # Add the currency symbol and return the formatted string
    return f"{currency_symbol} {formatted_value}"


async def format_shimmer_amount(value):
    # Convert the number to a float and then format it with 2 decimal places
    formatted_value = '{:.2f}'.format(float(value) / 1000000)
    return formatted_value

async def get_coingecko_exchange_data():
    """Get Coingecko exchange data"""
    headers = {"accept": "application/json"}
    try:
        exchange_response = requests.get(coingecko_exchange_url, headers=headers, timeout=10)  # Set a timeout of 10 seconds
        exchange_response.raise_for_status()  # Raise HTTPError for bad requests (4xx and 5xx status codes)
        logger.debug("Coingecko exchange response: %s", exchange_response.text)
    
        if exchange_response.status_code == 200:
            # Extract and parse the JSON response
            exchange_response = exchange_response.json()

            # Extract and sum the respective USD converted volumes for USD and USDT
            usd_volume = 0
            usd_price = 0
            usdt_volume = 0
            twentyfourh_volume = 0

            for ticker in exchange_response["tickers"]:
                if ticker["target"] == "USD":
                    usd_volume += ticker["converted_volume"]["usd"]
                    usd_price += ticker["last"]
                elif ticker["target"] == "USDT":
                    usdt_volume += ticker["converted_volume"]["usd"]
            
            logger.debug("Total USD Converted Volume for USD: %s", usd_volume)
            logger.debug("Last USD Price: %s", usd_price)
            logger.debug("Total USD Converted Volume for USDT: %s", usdt_volume)
            twentyfourh_volume = usd_volume + usdt_volume
            logger.debug("Total USD Converted 24h Volume for Shimmer: %s", twentyfourh_volume)
            # Format the integer as a dollar value with a currency separator
            formatted_volume = await format_currency(twentyfourh_volume)
            formatted_usd_price = await format_currency(usd_price)

            # Log the formatted 24-hour volume
            logger.debug("Total USD formatted 24h Volume for Shimmer: %s", formatted_volume)
            logger.debug("Last USD formatted price for Shimmer: %s", formatted_usd_price)
            return {"usd_price": formatted_usd_price, "total_volume": formatted_volume}

        else:
            logger.debug("Error: Unable to fetch data from the API.")

    except requests.exceptions.Timeout:
        logger.error("Coingecko API request timed out.")
    except requests.exceptions.HTTPError as errh:
        logger.error("HTTP Error occurred: %s", errh)
    except requests.exceptions.RequestException as err:
        logger.error("Request Exception occurred: %s", err)
    


async def get_bitfinex_book_data():
    """Get Bitfinex order book"""
    headers = {"accept": "application/json"}
    try:
        book_response = requests.get(bitfinex_book_url, headers=headers, timeout=10)
        book_response.raise_for_status()  # Raise HTTPError for bad requests (4xx and 5xx status codes)
        logger.debug("Bitfinex book response: %s", book_response.text)
    except requests.exceptions.Timeout:
        logger.error("Bitfinex API request timed out.")
    except requests.exceptions.HTTPError as errh:
        logger.error("HTTP Error occurred: %s", errh)
    except requests.exceptions.RequestException as err:
        logger.error("Request Exception occurred: %s", err)


async def get_defillama_data():
    """Get DefiLlama TVL data"""
    headers = {"accept": "*/*"}
    shimmer_tvl = None
    tvl_entries = []

    try:
        tvl_response = requests.get(defillama_url, headers=headers, timeout=10)
        tvl_response.raise_for_status()  # Raise HTTPError for bad requests (4xx and 5xx status codes)
        logger.debug("DefiLlama TVL response: %s", tvl_response.text)
        if tvl_response.status_code == 200:
            # Extract and parse the JSON response
            tvl_data = tvl_response.json()

            # Iterate through entries and collect TVL values
            for entry in tvl_data:
                gecko_id = entry.get("gecko_id")
                name = entry.get("name")
                tvl = entry.get("tvl")
                if name and tvl:
                    tvl_entries.append({"name": name, "tvl": tvl})

            # Sort the entries based on TVL values
            tvl_entries.sort(key=lambda x: x["tvl"], reverse=True)
            # Sort the list of dictionaries based on 'tvl' values in descending order
            sorted_data = sorted(tvl_entries, key=lambda x: x['tvl'], reverse=True)

            # Extract gecko_ids from the sorted list
            sorted_gecko_ids = [entry['name'] for entry in sorted_data]

            logger.debug(sorted_gecko_ids)

            # Find the rank of "shimmer" TVL
            for index, entry in enumerate(tvl_entries, start=1):
                if entry["name"] == "ShimmerEVM":
                    shimmer_tvl = entry["tvl"]
                    rank = index
                    break

            if shimmer_tvl is not None:
                # Format the integer as a dollar value with a currency separator
                formatted_tvl = await format_currency(shimmer_tvl)
                logger.debug("Shimmer TVL Value: %s", formatted_tvl)
                logger.debug("Shimmer TVL Rank: %s", rank)
                return {"shimmer_tvl":  formatted_tvl, "shimmer_rank": rank}
            else:
                logger.debug("Shimmer TVL Value not found in the response.")

        # Extract and sum the respective USD converted volumes for USD and USDT
    except requests.exceptions.Timeout:
        logger.error("DefiLlama API request timed out.")
    except requests.exceptions.HTTPError as errh:
        logger.error("HTTP Error occurred: %s", errh)
    except requests.exceptions.RequestException as err:
        logger.error("Request Exception occurred: %s", err)



async def get_geckoterminal_data():
    """Get GeckoTerminal Defi Volume data"""
    headers = {"accept": "application/json"}
    total_defi_volume_usd_h24 = 0
    total_buy_tx_h24 = 0
    total_sell_tx_h24 = 0
    page = 1

    try:
        while True:
            # Make a request to the GeckoTerminal API with the current page number
            defi_volume = requests.get(geckoterminal_url + f"?page={page}", headers=headers, timeout=10)
            defi_volume.raise_for_status()  # Raise HTTPError for bad requests (4xx and 5xx status codes)
            if defi_volume.status_code == 200:
                defi_volume_json = defi_volume.json()
                # Extract and parse the JSON response
                defi_volume_data = defi_volume_json.get("data", [])

                for entry in defi_volume_data:
                    h24_volume = float(entry["attributes"]["volume_usd"]["h24"])
                    total_defi_volume_usd_h24 += h24_volume

                    # Extract transactions data for h24
                    transactions_h24 = entry["attributes"]["transactions"]["h24"]
                    buys_h24 = transactions_h24.get("buys", 0)
                    sells_h24 = transactions_h24.get("sells", 0)
                    # Perform operations with buys_h24 and sells_h24 as needed
                    total_buy_tx_h24 += buys_h24
                    total_sell_tx_h24 += sells_h24

                logger.debug("Total USD 24h Volume for all pools: %s", total_defi_volume_usd_h24)
                logger.debug("Total Buy 24h transactions all pools: %s", total_buy_tx_h24)
                logger.debug("Total Sell 24h transactions all pools: %s", total_sell_tx_h24)

                if total_defi_volume_usd_h24 > 0:
                    if total_buy_tx_h24 > 0 and total_sell_tx_h24 > 0:
                        formatted_defi_volume = await format_currency(total_defi_volume_usd_h24)
                        logger.debug("Shimmer Defi Volume: %s", formatted_defi_volume)
                        total_defi_tx_24h = total_buy_tx_h24 + total_sell_tx_h24
                        return {"defi_total_volume":  formatted_defi_volume, "total_defi_tx_24h": total_defi_tx_24h}
                else:
                    logger.debug("Shimmer Total Volume not found in the response.")
            elif defi_volume.status_code == 404:
                logger.error("404 Client Error: Not Found for URL: %s", defi_volume.url)
            else:
                logger.error("Unexpected status code: %s", defi_volume.status_code)

    except requests.exceptions.Timeout:
        logger.error("GeckoTerminal API request timed out.")
    except requests.exceptions.HTTPError as errh:
        logger.error("HTTP Error occurred: %s", errh)
    except requests.exceptions.RequestException as err:
        logger.error("Request Exception occurred: %s", err)
    except Exception as e:
        logger.error("An unexpected error occurred: %s", e)


async def get_shimmer_data():
    """Get Shimmer Explorer API data"""
    headers = {"accept": "application/json"}
    try:
        shimmer_api_response = requests.get(shimmer_explorer_api_url, headers=headers, timeout=10)
        shimmer_api_response.raise_for_status()
        logger.debug("Shimmer Explorer API response: %s", shimmer_api_response.text)

        if shimmer_api_response.status_code == 200:
            # Extract and parse the JSON response
            shimmer_api_response = shimmer_api_response.json()
            
            response_output_id = shimmer_api_response.get("items", [])[0]
            shimmer_onchain_token_amount = None

            if response_output_id:
                output_url = f"https://api.shimmer.network/api/core/v2/outputs/{response_output_id}"
                while True:
                    response_output_id = requests.get(output_url)
                    output_id_data = response_output_id.json()

                    if output_id_data.get("metadata", {}).get("isSpent"):
                        item_content = output_id_data.get("metadata", {}).get("transactionIdSpent")
                        output_url = f"https://api.shimmer.network/api/core/v2/outputs/{item_content}"
                    else:
                        shimmer_onchain_token_amount = output_id_data.get("output", {}).get("amount")
                        break
            
            if shimmer_onchain_token_amount is not None:
                # Format glow to SMR
                shimmer_onchain_token_amount = await format_shimmer_amount(shimmer_onchain_token_amount)
                # Format the integer as a value with a currency separator
                formatted_shimmer_onchain_token_amount = await format_currency(shimmer_onchain_token_amount, "SMR")
                logger.debug("Shimmer On Chain Amount: %s", formatted_shimmer_onchain_token_amount)
                return {"shimmer_onchain_token_amount":  formatted_shimmer_onchain_token_amount}
            else:
                logger.debug("Shimmer TVL Value not found in the response.")

        else:
            logger.debug("Error: Unable to fetch data from the API.")

    except requests.exceptions.Timeout:
        logger.error("Shimmer API request timed out.")
    except requests.exceptions.HTTPError as errh:
        logger.error("HTTP Error occurred: %s", errh)
    except requests.exceptions.RequestException as err:
        logger.error("Request Exception occurred: %s", err)

async def build_embed():
    """Here we save a pickel file for the Discord embed message"""
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    coingecko_data = await get_coingecko_exchange_data()
    defillama_data = await get_defillama_data()
    geckoterminal_data = await get_geckoterminal_data()
    shimmer_data = await get_shimmer_data()

    try:
        usd_price = coingecko_data["usd_price"]
        total_volume = coingecko_data["total_volume"]
        defi_total_volume = geckoterminal_data["defi_total_volume"]
        total_defi_tx_24h = geckoterminal_data["total_defi_tx_24h"]
        shimmer_tvl = defillama_data["shimmer_tvl"]
        shimmer_rank = defillama_data["shimmer_rank"]
        shimmer_onchain_token_amount = shimmer_data["shimmer_onchain_token_amount"]

        # Create an embed instance
        embed = discord.Embed(title="Shimmer Market Data", color=0x00FF00)

        # Add fields to the embed
        embed.add_field(name="Price (Coingecko)", value=usd_price, inline=False)
        embed.add_field(name="24h Volume (Bitfinex)", value=total_volume, inline=False)
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.add_field(name="Defi Data", value="\u200b", inline=False)
        embed.add_field(name="Shimmer Rank (DefiLlama)", value=shimmer_rank, inline=True)
        embed.add_field(name="Shimmer Onchain Amount (Shimmer API)", value=shimmer_onchain_token_amount, inline=True)
        embed.add_field(name="Total Value Locked (DefiLlama)", value=shimmer_tvl, inline=True)
        embed.add_field(name="24h DeFi Transactions (DefiLlama)", value=total_defi_tx_24h, inline=True)
        embed.add_field(name="24h DeFi Volume (GeckoTerminal)", value=defi_total_volume, inline=True)

        # Add a blank field for separation
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        # Add additional information
        embed.add_field(name="Sources", value="Bitfinex, Coingecko, DefiLlama, GeckoTerminal, Shimmer API", inline=False)

        # Set the footer
        embed.set_footer(text="Data updated every 24h; last updated: " + current_time)

        with open("assets/embed_shimmer_market_data.pkl", "wb") as f:
            pickle.dump(embed, f)
    except Exception:
        logger.info(traceback.format_exc())


async def main():
    await build_embed()


if __name__ == "__main__":
    main()