
import pandas as pd

def clean(df, row):
    try:
        return df.loc[row].iloc[0]
    except (KeyError, IndexError):
        return None

def signal(Tscore):
    if Tscore >= 19:
        return "BUY"
    elif Tscore >= 12:
        return "KEEP"
    else:
        return "SELL"