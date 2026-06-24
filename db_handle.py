from pymongo import MongoClient
import pandas as pd
import csv

client = MongoClient("mongodb://localhost:27017/")

db = client['Leads']

print(db.list_collection_names())

data = db['searched_queries']

df = list(data.find({}))

df = pd.DataFrame(df)

df = df.drop("_id" ,axis=1)

print(df)

df.to_csv("data.csv", index=False)