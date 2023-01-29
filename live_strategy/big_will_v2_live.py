import sys
sys.path.append('../cBot-Project/utilities')
from custom_indicators import CustomIndocators as ci
from spot_ftx import SpotFtx
import pandas as pd
import ta
import ccxt
from socket import MsgFlag
from datetime import datetime
import time
import discord

now = datetime.now()
print(now.strftime("%d-%m %H:%M:%S"))

ftx = SpotFtx(
        apiKey='',
        secret='',
        subAccountName=''
    )

pairList = [
        "BTC/USD",
        "ETH/USD",
        "BNB/USD",
        "XRP/USD",
        "SOL/USD",
        "FTT/USD",
        "CHZ/USD",
        "DOGE/USD",
        "MATIC/USD",
        "AVAX/USD"
]

subAccountName='EvilBigWill'
timeframe = '1h'

MESSAGE_TEMPLATE = {
  "message_sell" : "{} : Vente {} à {} ",
  "message_keep" : "{} : Conserver {} ",
  "message_buy" : "{} : Achat de {} {} à {} USD ",
  "message_wallet" : "{} : Mon Wallet {} USD ",
  "message_erreur" : "{} : Impossible de récupérer les {} dernières bougies de {}."
}
message_list = []
# -- Indicator variable --
stochWindow = 14
willWindow = 14
trixLength = 9
trixSignal = 21

# -- Hyper parameters --
maxOpenPosition = 2
stochOverBought = 0.80
stochOverSold = 0.20
TpPct = 5

dfList = {}
nbOfCandles=210
ratio = [int((nbOfCandles*(100/(i+1)))/100)for i in range(0,3)]
idex = 0

for pair in pairList:
    request_success = False
    while(request_success == False):
        try :
            print(pair)
            df = ftx.get_last_historical(pair, timeframe, nbOfCandles)
            print(df)
            dfList[pair.replace('/USD','')] = df
            request_success = True
        except Exception as err:
            print(f"Erreur, détails : {err}")
            message_list.append(MESSAGE_TEMPLATE['message_erreur'].format(subAccountName, nbOfCandles, pair))
            
for coin in dfList:
    # -- Drop all columns we do not need --
    dfList[coin].drop(columns=dfList[coin].columns.difference(['open','high','low','close','volume']), inplace=True)

    dfList[coin]['TRIX'] = ta.trend.ema_indicator(ta.trend.ema_indicator(ta.trend.ema_indicator(close=dfList[coin]['close'], window=trixLength), window=trixLength), window=trixLength)
    dfList[coin]['TRIX_PCT'] = dfList[coin]["TRIX"].pct_change()*100
    dfList[coin]['TRIX_SIGNAL'] = ta.trend.sma_indicator(dfList[coin]['TRIX_PCT'],trixSignal)
    dfList[coin]['TRIX_HISTO'] = dfList[coin]['TRIX_PCT'] - dfList[coin]['TRIX_SIGNAL']
    dfList[coin]['STOCH_RSI'] = ta.momentum.stochrsi(close=dfList[coin]['close'], window=14, smooth1=3, smooth2=3)
    dfList[coin]['ema1'] = ta.trend.ema_indicator(close = dfList[coin]['close'], window = 5) # Moyenne exponentielle 1
    dfList[coin]['ema2'] = ta.trend.ema_indicator(close = dfList[coin]['close'], window = 15) # Moyenne exponentielle 2
    dfList[coin]['ema3'] = ta.trend.ema_indicator(close = dfList[coin]['close'], window = 50) # Moyenne exponentielle 3
    dfList[coin]['ema4'] = ta.trend.ema_indicator(close = dfList[coin]['close'], window = 100) # Moyenne exponentielle 4
    dfList[coin]['ema5'] = ta.trend.ema_indicator(close = dfList[coin]['close'], window = 121) # Moyenne exponentielle 5
    dfList[coin]['ema6'] = ta.trend.ema_indicator(close = dfList[coin]['close'], window = 200) # Moyenne exponentielle 6

print("Data and Indicators loaded 100%")
# -- Condition to BUY market --
def buyCondition(row, previousRow=None):
    if (
        row ['TRIX_HISTO'] > 0
        and row['STOCH_RSI'] <= stochOverBought
        and row['ema1'] > row['ema2'] 
        and row['ema2'] > row['ema3'] 
        and row['ema3'] > row['ema4'] 
        and row['ema4'] > row['ema5']
        and row['ema5'] > row['ema6']
    ):
        return True
    else:
        return False

# -- Condition to SELL market --
def sellCondition(row, previousRow=None):
    if (
        row['TRIX_HISTO'] < 0 
        and row['STOCH_RSI'] >= stochOverSold
    ):
        return True
    else:
        return False
    
coinBalance = ftx.get_all_balance()
coinInUsd = ftx.get_all_balance_in_usd()
usdBalance = coinBalance['USD']
del coinBalance['USD']
del coinInUsd['USD']
totalBalanceInUsd = usdBalance + sum(coinInUsd.values())
coinPositionList = []
for coin in coinInUsd:
    if coinInUsd[coin] > 0.05 * totalBalanceInUsd:
        coinPositionList.append(coin)
openPositions = len(coinPositionList)

#Sell
for coin in coinPositionList:
        if sellCondition(dfList[coin].iloc[-2], dfList[coin].iloc[-3]) == True:
            openPositions -= 1
            symbol = coin+'/USD'
            cancel = ftx.cancel_all_open_order(symbol)
            time.sleep(1)
            sellPrice = float(ftx.convert_price_to_precision(symbol, ftx.get_bid_ask_price(symbol)['ask']))
            sell = ftx.place_market_order(symbol,'sell',coinBalance[coin])
            message_list.append(MESSAGE_TEMPLATE['message_sell'].format(subAccountName, str(coin), str(sellPrice)))
        else:
            message_list.append(MESSAGE_TEMPLATE['message_keep'].format(subAccountName, str(coin)))

#Buy
if openPositions < maxOpenPosition:
    for coin in dfList:
        if coin not in coinPositionList:
            if buyCondition(dfList[coin].iloc[-2], dfList[coin].iloc[-3]) == True and openPositions < maxOpenPosition:
                subAccountName='EvilBigWill'
                time.sleep(1)
                usdBalance = ftx.get_balance_of_one_coin('USD')
                symbol = coin+'/USD'

                buyPrice = float(ftx.convert_price_to_precision(symbol, ftx.get_bid_ask_price(symbol)['ask'])) 
                tpPrice = float(ftx.convert_price_to_precision(symbol, buyPrice + TpPct * buyPrice))
                buyQuantityInUsd = usdBalance * 1/(maxOpenPosition-openPositions)

                if openPositions == maxOpenPosition - 1:
                    buyQuantityInUsd = 0.95 * buyQuantityInUsd

                buyAmount = ftx.convert_amount_to_precision(symbol, buyQuantityInUsd/buyPrice)

                buy = ftx.place_market_order(symbol,'buy',buyAmount)
                time.sleep(2)
                tp = ftx.place_limit_order(symbol,'sell',buyAmount,tpPrice)
                try:
                    tp["id"]
                except:
                    time.sleep(2)
                    tp = ftx.place_limit_order(symbol,'sell',buyAmount,tpPrice)
                    pass
                message_list.append(MESSAGE_TEMPLATE['message_buy'].format(subAccountName, str(buyAmount), str(coin), str(buyPrice)))
                openPositions += 1

new_coin_in_usd = ftx.get_all_balance_in_usd()
for coin in new_coin_in_usd:
    new_coin_in_usd[coin] = str(round(new_coin_in_usd[coin], 2)) + " $"
message_list.append(MESSAGE_TEMPLATE['message_wallet'].format(subAccountName, str(usdBalance)))


TOKEN = ""
client = discord.Client()
@client.event
async def on_ready():
    print(f'{client.user} has connected to Discord!')
    msg = "\n".join(message_list) # join prend une list et à chaque élément de la list ajoute "\n" ou autre

    user = await client.fetch_user(367274701841629185)
    await user.send(msg)

    channel = client.get_channel(644965634819489827)
    await channel.send(msg)
    await client.close()


client.run(TOKEN)
