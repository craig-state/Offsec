import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path(".") 
CUSTOMERS_CSV = DATA_DIR / "customers.csv"
PRODUCTS_CSV  = DATA_DIR / "products.csv"
SALES_CSV     = DATA_DIR / "sales.csv"

def load_data():
    customers = pd.read_csv(CUSTOMERS_CSV, parse_dates=["CreatedDate"])
    products = pd.read_csv(PRODUCTS_CSV, parse_dates=["ReleaseDate"])
    sales = pd.read_csv(SALES_CSV, parse_dates=["OrderDate"])
    return customers, products, sales

def top_products_overall(sales, products, top_n=10):
    agg = sales.groupby("ProductID").agg(UnitsSold=("Quantity","sum"),
                                         Revenue=("Total","sum")).reset_index()
    agg = agg.merge(products[["ProductID","Name","Category"]], on="ProductID", how="left")
    return agg.sort_values("UnitsSold", ascending=False).head(top_n)

def top_products_in_country(sales, products, country="US", top_n=10):
    s = sales[sales["Country"] == country]
    return top_products_overall(s, products, top_n)

def top_customers_by_revenue(sales, customers, top_n=10):
    agg = sales.groupby("CustomerID").agg(TotalRevenue=("Total","sum"),
                                         Orders=("SaleID","count")).reset_index()
    agg = agg.merge(customers[["CustomerID","FirstName","LastName","Email"]], on="CustomerID", how="left")
    agg["CustomerName"] = agg["FirstName"].fillna("") + " " + agg["LastName"].fillna("")
    return agg.sort_values("TotalRevenue", ascending=False).head(top_n)

def monthly_sales_trend(sales):
    sales["YearMonth"] = sales["OrderDate"].dt.to_period("M")
    agg = sales.groupby("YearMonth").agg(MonthlyRevenue=("Total","sum"),
                                         Units=("Quantity","sum")).reset_index().sort_values("YearMonth")
    agg["YearMonth"] = agg["YearMonth"].astype(str)
    return agg

def product_profitability(sales, products, top_n=10):
    # join unit cost from products; approximate cost per sale = Cost * Quantity
    merged = sales.merge(products[["ProductID","Cost","Price"]], on="ProductID", how="left")
    merged["CostTotal"] = merged["Cost"] * merged["Quantity"]
    merged["Profit"] = merged["Total"] - merged["CostTotal"]
    agg = merged.groupby("ProductID").agg(UnitsSold=("Quantity","sum"),
                                         Revenue=("Total","sum"),
                                         CostTotal=("CostTotal","sum"),
                                         Profit=("Profit","sum")).reset_index()
    agg = agg.merge(products[["ProductID","Name","Category"]], on="ProductID", how="left")
    return agg.sort_values("Profit", ascending=False).head(top_n)

def sales_by_state_us(sales):
    us = sales[sales["Country"] == "US"]
    agg = us.groupby("State").agg(Revenue=("Total","sum"), Units=("Quantity","sum")).reset_index().sort_values("Revenue", ascending=False)
    return agg

def main():
    customers, products, sales = load_data()
    print("Loaded datasets: customers={}, products={}, sales={}".format(len(customers), len(products), len(sales)))
    print("\nTop products overall (by units sold):")
    print(top_products_overall(sales, products, top_n=10).to_string(index=False))

    print("\nTop products in US (by units sold):")
    print(top_products_in_country(sales, products, country="US", top_n=10).to_string(index=False))

    print("\nTop customers by revenue:")
    print(top_customers_by_revenue(sales, customers, top_n=10).to_string(index=False))

    print("\nMonthly sales trend (last 12 months):")
    ms = monthly_sales_trend(sales)
    print(ms.tail(12).to_string(index=False))

    print("\nTop products by profitability:")
    print(product_profitability(sales, products, top_n=10).to_string(index=False))

    print("\nSales by US state:")
    print(sales_by_state_us(sales).to_string(index=False))

    # Optionally save summaries
    out = Path("analysis_outputs")
    out.mkdir(exist_ok=True)
    top_products_overall(sales, products, top_n=50).to_csv(out/"top_products_overall.csv", index=False)
    top_products_in_country(sales, products, country="US", top_n=50).to_csv(out/"top_products_us.csv", index=False)
    top_customers_by_revenue(sales, customers, top_n=100).to_csv(out/"top_customers_by_revenue.csv", index=False)
    monthly_sales_trend(sales).to_csv(out/"monthly_sales_trend.csv", index=False)
    product_profitability(sales, products, top_n=100).to_csv(out/"product_profitability.csv", index=False)
    sales_by_state_us(sales).to_csv(out/"sales_by_state_us.csv", index=False)

    print("\nSaved CSV summaries to ./analysis_outputs/")

if __name__ == "__main__":
    main()
