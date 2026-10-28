"""
SweetShop AI OS
A GitHub-ready Streamlit control centre for sweet-shop sales, demand, stock,
customer patterns, festival/weather context, production planning and deliveries.

Quick start:
  pip install -r requirements.txt
  streamlit run app.py

This is a single-file app by design. It uses SQLite locally and synthetic demo data.
Do not treat demo records or baseline forecasts as real business evidence.
"""
from __future__ import annotations

import io, os, json, math, random, sqlite3, hashlib, secrets
from datetime import date, datetime, timedelta, time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

APP_NAME = "SweetShop AI OS"
DB_FILE = Path(os.getenv("SWEETSHOP_DB", "sweetshop_ai_os.db"))
RNG = np.random.default_rng(42)

st.set_page_config(page_title=APP_NAME, page_icon="🍬", layout="wide", initial_sidebar_state="expanded")

# ─────────────────────────────────────────────────────────────────────────────
# 1. DATABASE LAYER
# ─────────────────────────────────────────────────────────────────────────────
SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS products(
 id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT UNIQUE, name TEXT UNIQUE NOT NULL,
 category TEXT NOT NULL DEFAULT 'Other', unit TEXT NOT NULL DEFAULT 'piece',
 selling_price REAL NOT NULL DEFAULT 0, unit_cost REAL NOT NULL DEFAULT 0,
 shelf_life_days INTEGER NOT NULL DEFAULT 3, reorder_level REAL NOT NULL DEFAULT 5,
 supplier TEXT DEFAULT '', active INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS customers(
 id INTEGER PRIMARY KEY AUTOINCREMENT, customer_code TEXT UNIQUE NOT NULL,
 display_name TEXT DEFAULT '', phone TEXT DEFAULT '', area TEXT DEFAULT '',
 segment TEXT DEFAULT 'Regular', marketing_consent INTEGER DEFAULT 0,
 created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sales(
 id INTEGER PRIMARY KEY AUTOINCREMENT, sold_at TEXT NOT NULL,
 product_id INTEGER NOT NULL REFERENCES products(id), quantity REAL NOT NULL,
 unit_price REAL NOT NULL, discount REAL NOT NULL DEFAULT 0,
 channel TEXT NOT NULL DEFAULT 'Walk-in', customer_id INTEGER REFERENCES customers(id),
 order_id TEXT DEFAULT '', payment_method TEXT DEFAULT 'UPI', promotion TEXT DEFAULT '',
 occasion TEXT DEFAULT '', notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS daily_context(
 day TEXT PRIMARY KEY, max_temp_c REAL, min_temp_c REAL, rainfall_mm REAL DEFAULT 0,
 humidity_pct REAL, festival TEXT DEFAULT '', holiday INTEGER DEFAULT 0,
 school_open INTEGER DEFAULT 1, local_event TEXT DEFAULT '', promotion TEXT DEFAULT '',
 competitor_note TEXT DEFAULT '', footfall INTEGER, stockout_products TEXT DEFAULT '',
 weather_source TEXT DEFAULT '', notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS stock_movements(
 id INTEGER PRIMARY KEY AUTOINCREMENT, moved_at TEXT NOT NULL,
 product_id INTEGER NOT NULL REFERENCES products(id), movement_type TEXT NOT NULL,
 quantity REAL NOT NULL, unit_cost REAL DEFAULT 0, batch_code TEXT DEFAULT '',
 expiry_date TEXT, supplier TEXT DEFAULT '', reference TEXT DEFAULT '', notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS ingredients(
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, unit TEXT DEFAULT 'kg',
 on_hand REAL DEFAULT 0, reorder_level REAL DEFAULT 0, unit_cost REAL DEFAULT 0,
 supplier TEXT DEFAULT '', shelf_life_days INTEGER DEFAULT 30
);
CREATE TABLE IF NOT EXISTS recipes(
 id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL REFERENCES products(id),
 ingredient_id INTEGER NOT NULL REFERENCES ingredients(id), qty_per_unit REAL NOT NULL,
 UNIQUE(product_id, ingredient_id)
);
CREATE TABLE IF NOT EXISTS deliveries(
 id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL, order_date TEXT NOT NULL,
 promised_at TEXT, delivered_at TEXT, area TEXT DEFAULT '', distance_km REAL DEFAULT 0,
 delivery_fee REAL DEFAULT 0, driver TEXT DEFAULT '', status TEXT DEFAULT 'Pending',
 order_value REAL DEFAULT 0, item_summary TEXT DEFAULT '', customer_rating REAL,
 delay_reason TEXT DEFAULT '', notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS suppliers(
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, contact TEXT DEFAULT '',
 lead_time_days INTEGER DEFAULT 1, reliability_pct REAL DEFAULT 90, minimum_order REAL DEFAULT 0,
 notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS promotions(
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, start_date TEXT, end_date TEXT,
 discount_pct REAL DEFAULT 0, channel TEXT DEFAULT 'All', spend REAL DEFAULT 0, notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS audit_log(
 id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, entity TEXT, entity_id TEXT,
 detail TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

def db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    with db() as conn:
        conn.executescript(SCHEMA)
        conn.commit()

def q(sql, params=()):
    with db() as conn:
        return pd.read_sql_query(sql, conn, params=params)

def run(sql, params=()):
    with db() as conn:
        cur=conn.execute(sql,params)
        conn.commit()
        return cur.lastrowid

def audit(action, entity, entity_id="", detail=""):
    run("INSERT INTO audit_log(action,entity,entity_id,detail) VALUES(?,?,?,?)",
        (action,entity,str(entity_id),str(detail)[:1000]))

init_db()

# ─────────────────────────────────────────────────────────────────────────────
# 2. DEMO DATA — clearly synthetic, never silently mixed with real imports
# ─────────────────────────────────────────────────────────────────────────────
def seed_demo():
    if q("SELECT id FROM products LIMIT 1").shape[0]:
        return
    catalog=[
        ("S001","Kaju Katli","Premium Sweets","kg",900,590,5,4,"Premium Foods"),
        ("S002","Gulab Jamun","Hot Sweets","piece",25,12,2,30,"Dairy Supplier"),
        ("S003","Rasgulla","Bengali Sweets","piece",22,11,3,30,"Dairy Supplier"),
        ("S004","Motichoor Laddu","Laddu","kg",420,260,4,3,"Sweet Ingredients Co"),
        ("S005","Soan Papdi","Dry Sweets","kg",360,220,30,3,"Premium Foods"),
        ("S006","Jalebi","Hot Sweets","kg",300,150,1,2,"Sweet Ingredients Co"),
        ("S007","Samosa","Snacks","piece",18,8,1,40,"Kitchen Supplier"),
        ("S008","Milk Cake","Milk Sweets","kg",480,300,4,3,"Dairy Supplier"),
        ("S009","Chocolate Barfi","Fusion Sweets","kg",550,330,4,3,"Premium Foods"),
        ("S010","Namkeen Mix","Snacks","kg",260,155,30,4,"Kitchen Supplier"),
        ("S011","Peda","Milk Sweets","kg",450,275,5,3,"Dairy Supplier"),
        ("S012","Besan Laddu","Laddu","kg",390,235,7,3,"Sweet Ingredients Co"),
        ("S013","Imarti","Hot Sweets","kg",320,165,1,2,"Sweet Ingredients Co"),
        ("S014","Dry Fruit Box","Gift Boxes","box",1250,820,45,2,"Packaging Supplier"),
    ]
    with db() as conn:
        conn.executemany("""INSERT INTO products(sku,name,category,unit,selling_price,unit_cost,
        shelf_life_days,reorder_level,supplier) VALUES(?,?,?,?,?,?,?,?,?)""",catalog)
        customers=[]
        areas=["Shankar Nagar","Telibandha","Pandri","Avanti Vihar","Civil Lines","Devendra Nagar","Mowa"]
        segments=["Regular","Family","Office","Event","New","Wholesale"]
        for i in range(1,121):
            customers.append((f"C{i:04d}",f"Demo Customer {i}",f"9{random.randint(100000000,999999999)}",
                             random.choice(areas),random.choice(segments),random.choice([0,0,1])))
        conn.executemany("INSERT INTO customers(customer_code,display_name,phone,area,segment,marketing_consent) VALUES(?,?,?,?,?,?)",customers)
        pids=[x[0] for x in conn.execute("SELECT id FROM products").fetchall()]
        cids=[x[0] for x in conn.execute("SELECT id FROM customers").fetchall()]
        start=date.today()-timedelta(days=179)
        sales=[]; contexts=[]
        for i in range(180):
            day=start+timedelta(days=i)
            festival=""
            if day.month in [10,11] and 15<=day.day<=31: festival="Festival season"
            elif day.month==8 and 5<=day.day<=25: festival="Raksha Bandhan season"
            elif day.month==3 and 1<=day.day<=15: festival="Holi season"
            max_temp=round(random.uniform(24,41),1)
            rain=round(random.choice([0,0,0,0,1,4,10,18]),1)
            contexts.append((day.isoformat(),max_temp,round(max_temp-random.uniform(5,10),1),rain,
                             random.randint(25,90),festival,int(day.weekday()>=5),1,
                             random.choice(["","Local fair","Cricket match","School event",""]),random.choice(["","Combo offer","No offer"]),
                             "",random.randint(45,280),"","synthetic demo","Synthetic demo data"))
            n=random.randint(25,60)
            for _ in range(n):
                pid=random.choice(pids); cid=random.choice(cids)
                prod=conn.execute("SELECT selling_price FROM products WHERE id=?",(pid,)).fetchone()[0]
                qty=random.choice([1,1,1,2,2,3,0.25,0.5])
                # Synthetic pattern for demonstrating the dashboard, not a real market claim.
                chance=0.72*(1.4 if festival else 1)*(1.15 if day.weekday()>=5 else 1)
                if random.random()>min(chance,0.98): continue
                sold=datetime.combine(day,time(hour=random.randint(8,21),minute=random.randint(0,59)))
                sales.append((sold.isoformat(sep=" "),pid,qty,prod,random.choice([0,0,0,5,10]),
                              random.choice(["Walk-in","WhatsApp","Phone","Online","Delivery","Catering"]),
                              cid,f"DEMO-{day:%y%m%d}-{random.randint(100,999)}",
                              random.choice(["UPI","Cash","Card"]),random.choice(["","Combo offer",""]),
                              festival,"Synthetic demo sale"))
        conn.executemany("""INSERT INTO daily_context(day,max_temp_c,min_temp_c,rainfall_mm,humidity_pct,
        festival,holiday,school_open,local_event,promotion,competitor_note,footfall,stockout_products,
        weather_source,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",contexts)
        conn.executemany("""INSERT INTO sales(sold_at,product_id,quantity,unit_price,discount,channel,
        customer_id,order_id,payment_method,promotion,occasion,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",sales)
        for pid in pids:
            conn.execute("""INSERT INTO stock_movements(moved_at,product_id,movement_type,quantity,
            unit_cost,batch_code,expiry_date,supplier,notes) VALUES(?,?,?,?,?,?,?,?,?)""",
            (datetime.now().isoformat(sep=" " ),pid,"IN",random.randint(20,150),0,"OPENING",
             (date.today()+timedelta(days=14)).isoformat(),"Demo supplier","Synthetic opening stock"))
        conn.execute("INSERT INTO suppliers(name,lead_time_days,reliability_pct) VALUES(?,?,?)",("Demo Supplier",2,92))
        conn.commit()

if os.getenv("SWEETSHOP_DEMO","1")=="1":
    seed_demo()

# ─────────────────────────────────────────────────────────────────────────────
# 3. DATA ACCESS / FEATURE ENGINEERING
# ─────────────────────────────────────────────────────────────────────────────
def load_sales():
    data=q("""SELECT s.*,p.sku,p.name product,p.category,p.unit,p.selling_price catalog_price,
    p.unit_cost,c.customer_code,c.display_name customer_name,c.area customer_area,c.segment customer_segment
    FROM sales s JOIN products p ON p.id=s.product_id LEFT JOIN customers c ON c.id=s.customer_id
    ORDER BY s.sold_at""")
    if data.empty: return data
    data["sold_at"]=pd.to_datetime(data["sold_at"],errors="coerce")
    data=data.dropna(subset=["sold_at"])
    data["day"]=data.sold_at.dt.date.astype(str)
    data["weekday"]=data.sold_at.dt.day_name()
    data["weekday_num"]=data.sold_at.dt.weekday
    data["month"]=data.sold_at.dt.month
    data["hour"]=data.sold_at.dt.hour
    data["is_weekend"]=(data.weekday_num>=5).astype(int)
    data["revenue"]=data.quantity*data.unit_price-data.discount.fillna(0)
    data["estimated_cost"]=data.quantity*data.unit_cost
    data["estimated_gross_profit"]=data.revenue-data.estimated_cost
    data["gross_margin_pct"]=np.where(data.revenue>0,data.estimated_gross_profit/data.revenue*100,0)
    return data

def load_inventory():
    return q("""SELECT p.id,p.sku,p.name,p.category,p.unit,p.selling_price,p.unit_cost,p.reorder_level,
    p.shelf_life_days,p.supplier,
    COALESCE(SUM(CASE WHEN m.movement_type IN ('IN','PRODUCTION','RETURN','ADJUSTMENT_IN') THEN m.quantity
      WHEN m.movement_type IN ('OUT','WASTE','SALE','ADJUSTMENT_OUT') THEN -m.quantity ELSE 0 END),0) stock
    FROM products p LEFT JOIN stock_movements m ON p.id=m.product_id
    WHERE p.active=1 GROUP BY p.id ORDER BY p.name""")

def load_context():
    d=q("SELECT * FROM daily_context ORDER BY day")
    if not d.empty:
        d["day"]=pd.to_datetime(d.day,errors="coerce")
    return d

def safe_money(v):
    try: return f"₹{float(v):,.0f}"
    except Exception: return "₹0"

def download_csv(frame, filename, key):
    st.download_button(f"Download {filename} CSV",frame.to_csv(index=False).encode("utf-8"),
                       file_name=filename.lower().replace(" ","_")+".csv",mime="text/csv",key=key)

sales=load_sales()
products=q("SELECT * FROM products WHERE active=1 ORDER BY name")
customers=q("SELECT * FROM customers ORDER BY id DESC")
inventory=load_inventory()
context=load_context()
deliveries=q("SELECT * FROM deliveries ORDER BY order_date DESC")

# ─────────────────────────────────────────────────────────────────────────────
# 4. SIDEBAR AND FILTERS
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.title("🍬 SweetShop AI OS")
st.sidebar.caption("A data-driven operating system for your sweet shop")
pages=[
 "Executive Dashboard","Product & Customer Intelligence","AI Demand Forecast",
 "Production Planner","Inventory & Expiry","Ingredients & Recipes",
 "Orders & Delivery Logistics","Weather & Festival Diary","Sales Entry & Imports",
 "Catalog & Customer CRM","Promotions & Experiments","Reports & Data Quality",
 "Settings & Data Export"
]
page=st.sidebar.radio("Navigate",pages)
st.sidebar.divider()
st.sidebar.caption("Demo dataset is synthetic. Check Settings before using real data.")

if not sales.empty:
    low=pd.to_datetime(sales.day).min().date(); high=pd.to_datetime(sales.day).max().date()
else: low=high=date.today()
date_filter=st.sidebar.date_input("Analytics date range",value=(low,high),min_value=low,max_value=max(high,date.today()))
if isinstance(date_filter,tuple) and len(date_filter)==2: dstart,dend=date_filter
else: dstart=dend=date_filter
filtered=sales.copy()
if not filtered.empty:
    filtered=filtered[(filtered.sold_at.dt.date>=dstart)&(filtered.sold_at.dt.date<=dend)]
    cats=sorted(filtered.category.dropna().unique())
    selected_cats=st.sidebar.multiselect("Product categories",cats,default=cats)
    if selected_cats: filtered=filtered[filtered.category.isin(selected_cats)]
    chs=sorted(filtered.channel.dropna().unique())
    selected_chs=st.sidebar.multiselect("Channels",chs,default=chs)
    if selected_chs: filtered=filtered[filtered.channel.isin(selected_chs)]

def heading(title, subtitle=None):
    st.title(title)
    if subtitle: st.caption(subtitle)

def metric_row(items):
    cols=st.columns(len(items))
    for col,(label,value,delta) in zip(cols,items):
        col.metric(label,value,delta)

def add_context_features(frame):
    if frame.empty: return frame
    daily=frame.groupby("day",as_index=False).agg(revenue=("revenue","sum"),quantity=("quantity","sum"),orders=("order_id","nunique"))
    if not context.empty:
        cx=context.copy(); cx["day"]=cx.day.dt.strftime("%Y-%m-%d")
        daily=daily.merge(cx[["day","max_temp_c","min_temp_c","rainfall_mm","humidity_pct","festival","holiday","school_open","local_event","promotion","footfall","stockout_products"]],on="day",how="left")
    return daily

# ─────────────────────────────────────────────────────────────────────────────
# 5. EXECUTIVE DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
if page=="Executive Dashboard":
    heading("SweetShop Command Centre","Sales performance, margins, demand patterns and operating alerts.")
    if filtered.empty:
        st.info("No sales in this date range. Add sales in Sales Entry & Imports.")
    else:
        revenue=float(filtered.revenue.sum()); profit=float(filtered.estimated_gross_profit.sum())
        orders=int(filtered.order_id.replace("",np.nan).nunique())
        units=float(filtered.quantity.sum())
        aov=revenue/max(1,orders)
        metric_row([("Net sales",safe_money(revenue),None),("Estimated gross profit",safe_money(profit),None),
                    ("Quantity sold",f"{units:,.1f}",None),("Orders",f"{orders:,}",None),
                    ("Average order value",safe_money(aov),None)])
        st.caption("Estimated profit uses today's catalog cost, not cost at time of sale. It excludes tax, labour, rent, wastage and delivery overhead.")
        daily=filtered.groupby("day",as_index=False).agg(revenue=("revenue","sum"),profit=("estimated_gross_profit","sum"),quantity=("quantity","sum"))
        st.plotly_chart(px.line(daily,x="day",y="revenue",markers=True,title="Daily net sales"),use_container_width=True)
        left,right=st.columns(2)
        top=filtered.groupby("product",as_index=False).agg(revenue=("revenue","sum"),quantity=("quantity","sum")).sort_values("revenue",ascending=False).head(12)
        left.plotly_chart(px.bar(top,x="revenue",y="product",orientation="h",title="Best sellers by revenue"),use_container_width=True)
        weekday=filtered.groupby("weekday",as_index=False).agg(revenue=("revenue","sum"),quantity=("quantity","sum"))
        order=["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        weekday["weekday"]=pd.Categorical(weekday.weekday,categories=order,ordered=True)
        weekday=weekday.sort_values("weekday")
        right.plotly_chart(px.bar(weekday,x="weekday",y="revenue",title="Sales by weekday"),use_container_width=True)
        st.subheader("Operations alerts")
        lowstock=inventory[inventory.stock<inventory.reorder_level] if not inventory.empty else pd.DataFrame()
        if not lowstock.empty:
            st.warning(f"{len(lowstock)} products are below their reorder level.")
            st.dataframe(lowstock[["name","stock","unit","reorder_level","supplier"]],use_container_width=True,hide_index=True)
        else: st.success("No products below reorder level in the current stock ledger.")
        if not context.empty:
            latest=context.dropna(subset=["day"]).tail(1)
            if not latest.empty:
                st.caption("Latest context record: "+str(latest.iloc[0].day.date()))
        download_csv(daily,"Daily Sales","overview_daily_csv")

# ─────────────────────────────────────────────────────────────────────────────
# 6. CUSTOMER AND PRODUCT INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────
elif page=="Product & Customer Intelligence":
    heading("Product & Customer Intelligence","Understand which products sell to whom, at what time, and on which day.")
    if filtered.empty: st.info("No filtered sales available.")
    else:
        left,right=st.columns(2)
        heat=filtered.groupby(["product","weekday"],as_index=False).agg(quantity=("quantity","sum"))
        left.plotly_chart(px.density_heatmap(heat,x="weekday",y="product",z="quantity",histfunc="sum",title="Product demand by weekday"),use_container_width=True)
        hour=filtered.groupby("hour",as_index=False).agg(revenue=("revenue","sum"),transactions=("id","count"))
        right.plotly_chart(px.bar(hour,x="hour",y="revenue",title="Peak sales hours"),use_container_width=True)
        st.subheader("Product scorecard")
        score=filtered.groupby(["product","category"],as_index=False).agg(
            quantity=("quantity","sum"),revenue=("revenue","sum"),estimated_profit=("estimated_gross_profit","sum"),
            transactions=("id","count"),avg_price=("unit_price","mean"))
        score["estimated_margin_pct"]=np.where(score.revenue>0,100*score.estimated_profit/score.revenue,0)
        score=score.sort_values("revenue",ascending=False)
        st.dataframe(score,use_container_width=True,hide_index=True)
        st.subheader("Customer segment and area")
        a,b=st.columns(2)
        seg=filtered[filtered.customer_segment.notna()].groupby("customer_segment",as_index=False).agg(revenue=("revenue","sum"),transactions=("id","count"))
        if not seg.empty: a.plotly_chart(px.bar(seg,x="customer_segment",y="revenue",title="Revenue by segment"),use_container_width=True)
        areas=filtered[filtered.customer_area.notna()].groupby("customer_area",as_index=False).agg(revenue=("revenue","sum"),orders=("order_id","nunique"))
        if not areas.empty: b.plotly_chart(px.bar(areas,x="customer_area",y="revenue",title="Revenue by customer area"),use_container_width=True)
        st.subheader("Frequently bought together (exploratory)")
        basket=filtered[filtered.order_id.notna() & (filtered.order_id!="")].groupby("order_id").product.apply(lambda x: sorted(set(x)))
        pairs={}
        for items in basket:
            for i in range(len(items)):
                for j in range(i+1,len(items)):
                    key=(items[i],items[j]); pairs[key]=pairs.get(key,0)+1
        pairdf=pd.DataFrame([{"product_a":k[0],"product_b":k[1],"orders_together":v} for k,v in pairs.items()])
        if not pairdf.empty: st.dataframe(pairdf.sort_values("orders_together",ascending=False).head(25),use_container_width=True,hide_index=True)
        else: st.info("Record consistent order IDs to calculate basket combinations.")
        download_csv(score,"Product Scorecard","product_score_csv")

# ─────────────────────────────────────────────────────────────────────────────
# 7. MACHINE LEARNING FORECASTING
# ─────────────────────────────────────────────────────────────────────────────
elif page=="AI Demand Forecast":
    heading("AI Demand Forecast","Compare interpretable baselines with optional machine-learning models.")
    st.info("Forecasts are decision support, not certainty. Validate on held-out dates; festivals, stockouts and new products can break historical patterns.")
    if sales.empty:
        st.warning("Add sales first.")
    else:
        from sklearn.metrics import mean_absolute_error, mean_squared_error
        from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor, ExtraTreesRegressor
        from sklearn.linear_model import Ridge
        horizon=st.slider("Forecast horizon (days)",1,30,14)
        history_days=st.slider("History window (days)",30,180,90)
        chosen_product=st.selectbox("Product to forecast",["All products"]+sorted(sales.product.unique()))
        model_name=st.selectbox("Model",["Weekday baseline","Random Forest","Extra Trees","HistGradientBoosting","Ridge regression"])
        end_day=pd.to_datetime(sales.day).max().normalize()
        start_day=end_day-pd.Timedelta(days=history_days-1)
        hist=sales[sales.sold_at.dt.normalize().between(start_day,end_day)].copy()
        if chosen_product!="All products": hist=hist[hist.product==chosen_product]
        daily=hist.groupby(["day","product"],as_index=False).agg(y=("quantity","sum"),revenue=("revenue","sum"))
        daily["date"]=pd.to_datetime(daily.day)
        daily["weekday"]=daily.date.dt.weekday
        daily["month"]=daily.date.dt.month
        daily["dayofyear"]=daily.date.dt.dayofyear
        daily["weekofyear"]=daily.date.dt.isocalendar().week.astype(int)
        daily["trend"]=(daily.date-daily.date.min()).dt.days
        daily["is_weekend"]=(daily.weekday>=5).astype(int)
        cx=context.copy()
        if not cx.empty:
            cx["day"]=cx.day.dt.strftime("%Y-%m-%d")
            daily=daily.merge(cx[["day","max_temp_c","min_temp_c","rainfall_mm","humidity_pct","holiday","school_open","footfall"]],on="day",how="left")
        feature_cols=["weekday","month","dayofyear","weekofyear","trend","is_weekend","max_temp_c","min_temp_c","rainfall_mm","humidity_pct","holiday","school_open","footfall"]
        for col in feature_cols:
            if col not in daily: daily[col]=0
            daily[col]=pd.to_numeric(daily[col],errors="coerce")
            daily[col]=daily[col].fillna(daily[col].median() if daily[col].notna().any() else 0)
        if len(daily)<14:
            st.warning("At least 14 days of daily data are recommended for a meaningful comparison.")
        else:
            # Time-ordered holdout avoids random leakage.
            split=max(1,int(len(daily)*0.8))
            train=daily.iloc[:split].copy(); test=daily.iloc[split:].copy()
            if len(test)==0: test=daily.tail(min(7,len(daily))).copy(); train=daily.iloc[:-len(test)].copy()
            def weekday_predict(train_frame,test_frame):
                means=train_frame.groupby("weekday").y.mean().to_dict()
                overall=float(train_frame.y.mean()) if len(train_frame) else 0
                return np.array([means.get(int(w),overall) for w in test_frame.weekday])
            models={
                "Random Forest":RandomForestRegressor(n_estimators=250,min_samples_leaf=2,random_state=42,n_jobs=-1),
                "Extra Trees":ExtraTreesRegressor(n_estimators=250,min_samples_leaf=2,random_state=42,n_jobs=-1),
                "HistGradientBoosting":HistGradientBoostingRegressor(max_iter=150,l2_regularization=1.0,random_state=42),
                "Ridge regression":Ridge(alpha=2.0)
            }
            eval_rows=[]
            predictions={}
            for nm in ["Weekday baseline"]+list(models):
                try:
                    if nm=="Weekday baseline":
                        pred=weekday_predict(train,test)
                    else:
                        mdl=models[nm]
                        mdl.fit(train[feature_cols],train.y)
                        pred=mdl.predict(test[feature_cols])
                    pred=np.maximum(0,np.asarray(pred))
                    predictions[nm]=pred
                    eval_rows.append({"model":nm,"MAE":mean_absolute_error(test.y,pred),
                                      "RMSE":math.sqrt(mean_squared_error(test.y,pred))})
                except Exception as exc:
                    eval_rows.append({"model":nm,"MAE":np.nan,"RMSE":np.nan})
            metrics=pd.DataFrame(eval_rows).sort_values("MAE")
            st.subheader("Time-based validation")
            st.dataframe(metrics,use_container_width=True,hide_index=True)
            chosen_pred=predictions.get(model_name)
            if chosen_pred is not None:
                comparison=test[["date","y"]].copy()
                comparison["prediction"]=chosen_pred
                st.plotly_chart(px.line(comparison,x="date",y=["y","prediction"],markers=True,title=f"Holdout: actual vs {model_name}"),use_container_width=True)
            # Fit selected model on all observations and forecast future dates.
            future_dates=pd.date_range(end_day+pd.Timedelta(days=1),periods=horizon)
            products_to_forecast=sorted(hist.product.unique())
            forecast_rows=[]
            for product in products_to_forecast:
                sub=daily[daily.product==product].sort_values("date").copy()
                if sub.empty: continue
                future=pd.DataFrame({"date":future_dates})
                future["weekday"]=future.date.dt.weekday; future["month"]=future.date.dt.month
                future["dayofyear"]=future.date.dt.dayofyear
                future["weekofyear"]=future.date.dt.isocalendar().week.astype(int)
                future["trend"]=(future.date-daily.date.min()).dt.days
                future["is_weekend"]=(future.weekday>=5).astype(int)
                future["product"]=product
                future["day"]=future.date.dt.strftime("%Y-%m-%d")
                future=future.merge(cx[["day","max_temp_c","min_temp_c","rainfall_mm","humidity_pct","holiday","school_open","footfall"]] if not cx.empty else pd.DataFrame(columns=["day"]),on="day",how="left")
                for col in feature_cols:
                    if col not in future: future[col]=0
                    future[col]=pd.to_numeric(future[col],errors="coerce")
                    future[col]=future[col].fillna(sub[col].median() if col in sub and sub[col].notna().any() else 0)
                if model_name=="Weekday baseline":
                    pred=weekday_predict(sub,future)
                else:
                    mdl=models[model_name]
                    mdl.fit(sub[feature_cols],sub.y)
                    pred=mdl.predict(future[feature_cols])
                for dt,predv in zip(future_dates,np.maximum(0,pred)):
                    forecast_rows.append({"date":dt.date().isoformat(),"product":product,"forecast_quantity":round(float(predv),2),"model":model_name})
            forecast=pd.DataFrame(forecast_rows)
            if chosen_product!="All products": forecast=forecast[forecast.product==chosen_product]
            st.subheader("Forward forecast")
            if not forecast.empty:
                st.plotly_chart(px.line(forecast,x="date",y="forecast_quantity",color="product",title="Forecast quantity by product"),use_container_width=True)
                st.dataframe(forecast,use_container_width=True,hide_index=True)
                download_csv(forecast,"Demand Forecast","forecast_csv")
            st.caption("Current model features include calendar and recorded weather/holiday context. Festival labels are not automatically encoded yet; add reliable festival features before relying on festival forecasts.")

# ─────────────────────────────────────────────────────────────────────────────
# 8. PRODUCTION PLANNING
# ─────────────────────────────────────────────────────────────────────────────
elif page=="Production Planner":
    heading("Production Planner","Translate demand estimates into practical preparation quantities.")
    st.caption("Starter calculation: forecast demand plus a safety buffer minus current stock. It does not yet model batches, labour capacity, ingredients, or production yield.")
    if sales.empty: st.info("Add sales to begin.")
    else:
        window=st.slider("Demand history (days)",7,90,28)
        buffer_pct=st.slider("Safety buffer (%)",0,100,20)
        target_day=st.date_input("Plan production for",value=date.today()+timedelta(days=1))
        end_dt=pd.to_datetime(sales.day).max()
        hist=sales[sales.sold_at>=end_dt-pd.Timedelta(days=window-1)]
        wd=target_day.strftime("%A")
        prod=hist[hist.weekday==wd].groupby("product",as_index=False).agg(avg_qty=("quantity","mean"),days_seen=("day","nunique"))
        if prod.empty: prod=hist.groupby("product",as_index=False).agg(avg_qty=("quantity","mean"),days_seen=("day","nunique"))
        prod=prod.merge(inventory[["name","stock","unit","reorder_level"]].rename(columns={"name":"product"}),on="product",how="left")
        prod["forecast_qty"]=prod.avg_qty*(1+buffer_pct/100)
        prod["recommended_make_qty"]=(prod.forecast_qty-prod.stock.fillna(0)).clip(lower=0).round(2)
        prod["recommended_make_qty"]=prod.recommended_make_qty.round(2)
        st.dataframe(prod.sort_values("recommended_make_qty",ascending=False),use_container_width=True,hide_index=True)
        st.metric("Suggested total make quantity",f"{prod.recommended_make_qty.sum():,.1f}")
        download_csv(prod,"Production Plan","production_plan_csv")
        st.warning("Use product-specific shelf life and actual remaining sellable stock before production. Do not blindly manufacture forecast amounts.")

# ─────────────────────────────────────────────────────────────────────────────
# 9. INVENTORY & EXPIRY
# ─────────────────────────────────────────────────────────────────────────────
elif page=="Inventory & Expiry":
    heading("Inventory & Expiry","Stock ledger, reorder warnings, waste tracking and batch expiry.")
    if not inventory.empty:
        inv=inventory.copy()
        inv["status"]=np.where(inv.stock<inv.reorder_level,"REORDER","OK")
        metric_row([("Active products",str(len(inv)),None),("Below reorder",str(int((inv.status=="REORDER").sum())),None),
                    ("Estimated stock value",safe_money((inv.stock*inv.unit_cost).sum()),None)])
        st.dataframe(inv,use_container_width=True,hide_index=True)
        st.plotly_chart(px.bar(inv,x="name",y="stock",color="status",title="Stock by product"),use_container_width=True)
    st.subheader("Record stock movement")
    with st.form("stock_movement"):
        pnames=products.name.tolist()
        pname=st.selectbox("Product",pnames)
        movement=st.selectbox("Movement type",["IN","PRODUCTION","OUT","WASTE","RETURN","SALE","ADJUSTMENT_IN","ADJUSTMENT_OUT"])
        qty=st.number_input("Quantity in the product's configured unit",min_value=0.01,value=1.0,step=0.5)
        cost=st.number_input("Unit cost (₹)",min_value=0.0,value=0.0)
        batch=st.text_input("Batch code"); expiry=st.date_input("Expiry date",value=date.today()+timedelta(days=3))
        supplier=st.text_input("Supplier / source"); ref=st.text_input("Invoice / reference"); note=st.text_input("Notes")
        if st.form_submit_button("Save movement"):
            pid=int(products.loc[products.name==pname,"id"].iloc[0])
            run("""INSERT INTO stock_movements(moved_at,product_id,movement_type,quantity,unit_cost,batch_code,expiry_date,supplier,reference,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",(datetime.now().isoformat(sep=" "),pid,movement,qty,cost,batch,expiry.isoformat(),supplier,ref,note))
            audit("CREATE","stock_movement",pid,f"{movement} {qty} {pname}")
            st.success("Stock movement saved."); st.rerun()
    movements=q("""SELECT m.*,p.name product,p.unit FROM stock_movements m JOIN products p ON p.id=m.product_id ORDER BY moved_at DESC LIMIT 500""")
    st.subheader("Recent stock ledger")
    st.dataframe(movements,use_container_width=True,hide_index=True)
    download_csv(movements,"Stock Ledger","stock_ledger_csv")

# ─────────────────────────────────────────────────────────────────────────────
# 10. INGREDIENTS & RECIPES
# ─────────────────────────────────────────────────────────────────────────────
elif page=="Ingredients & Recipes":
    heading("Ingredients & Recipes","Track raw materials and estimate ingredient needs from a production plan.")
    ingredients=q("SELECT * FROM ingredients ORDER BY name")
    left,right=st.columns(2)
    with left:
        st.subheader("Add ingredient")
        with st.form("ingredient_add"):
            name=st.text_input("Ingredient name")
            unit=st.selectbox("Unit",["kg","g","litre","ml","piece","packet"])
            onhand=st.number_input("Opening stock",min_value=0.0,value=0.0)
            reorder=st.number_input("Reorder level",min_value=0.0,value=1.0)
            cost=st.number_input("Cost per unit (₹)",min_value=0.0,value=0.0)
            supplier=st.text_input("Supplier")
            shelf=st.number_input("Shelf life (days)",min_value=1,value=30)
            if st.form_submit_button("Save ingredient"):
                try:
                    run("INSERT INTO ingredients(name,unit,on_hand,reorder_level,unit_cost,supplier,shelf_life_days) VALUES(?,?,?,?,?,?,?)",
                        (name,unit,onhand,reorder,cost,supplier,int(shelf)))
                    audit("CREATE","ingredient",name)
                    st.success("Ingredient saved."); st.rerun()
                except Exception as ex: st.error(str(ex))
    with right:
        st.subheader("Current ingredients")
        if not ingredients.empty:
            ingredients["status"]=np.where(ingredients.on_hand<ingredients.reorder_level,"REORDER","OK")
            st.dataframe(ingredients,use_container_width=True,hide_index=True)
        else: st.info("No ingredients entered yet.")
    st.subheader("Define recipe usage")
    with st.form("recipe_form"):
        pn=st.selectbox("Product",products.name.tolist())
        ins=ingredients.name.tolist() if not ingredients.empty else []
        if ins: ing=st.selectbox("Ingredient",ins)
        else: ing=None; st.caption("Add an ingredient first.")
        qty=st.number_input("Ingredient quantity per 1 product unit",min_value=0.0001,value=0.1,format="%.4f")
        if st.form_submit_button("Save recipe") and ing:
            pid=int(products.loc[products.name==pn,"id"].iloc[0])
            iid=int(ingredients.loc[ingredients.name==ing,"id"].iloc[0])
            run("INSERT INTO recipes(product_id,ingredient_id,qty_per_unit) VALUES(?,?,?) ON CONFLICT(product_id,ingredient_id) DO UPDATE SET qty_per_unit=excluded.qty_per_unit",(pid,iid,qty))
            st.success("Recipe saved."); st.rerun()
    rec=q("""SELECT p.name product,i.name ingredient,i.unit ingredient_unit,r.qty_per_unit
    FROM recipes r JOIN products p ON p.id=r.product_id JOIN ingredients i ON i.id=r.ingredient_id ORDER BY p.name,i.name""")
    st.subheader("Recipe matrix")
    st.dataframe(rec,use_container_width=True,hide_index=True)
    st.subheader("Ingredient needs for a planned production run")
    if not rec.empty:
        with st.form("ingredient_need"):
            target_product=st.selectbox("Product to make",sorted(rec.product.unique()))
            units=st.number_input("Units / kg / boxes to produce",min_value=0.0,value=10.0)
            if st.form_submit_button("Calculate ingredients"):
                need=rec[rec.product==target_product].copy()
                need["planned_product_quantity"]=units
                need["ingredient_required"]=need.qty_per_unit*units
                st.dataframe(need,use_container_width=True,hide_index=True)
                st.caption("Confirm units and yield assumptions with your kitchen recipe before purchasing.")

# ─────────────────────────────────────────────────────────────────────────────
# 11. DELIVERY LOGISTICS
# ─────────────────────────────────────────────────────────────────────────────
elif page=="Orders & Delivery Logistics":
    heading("Orders & Delivery Logistics","Track delivery promises, delays, cost, route zones and customer feedback.")
    deliveries=q("SELECT * FROM deliveries ORDER BY order_date DESC")
    if not deliveries.empty:
        tmp=deliveries.copy()
        tmp["promised_at"]=pd.to_datetime(tmp.promised_at,errors="coerce")
        tmp["delivered_at"]=pd.to_datetime(tmp.delivered_at,errors="coerce")
        delivered=tmp[tmp.status.str.lower()=="delivered"]
        late=int(((delivered.delivered_at>delivered.promised_at)&delivered.promised_at.notna()&delivered.delivered_at.notna()).sum())
        ontime=max(0,len(delivered)-late)
        metric_row([("Delivery records",str(len(tmp)),None),("Delivered",str(len(delivered)),None),
                    ("Late deliveries",str(late),None),("On-time rate",f"{ontime/max(1,len(delivered))*100:.1f}%",None)])
        st.dataframe(tmp,use_container_width=True,hide_index=True)
        if tmp.area.notna().any():
            zone=tmp.groupby("area",as_index=False).agg(deliveries=("id","count"),distance_km=("distance_km","sum"),fees=("delivery_fee","sum"),order_value=("order_value","sum"))
            st.plotly_chart(px.bar(zone,x="area",y="deliveries",title="Delivery volume by area"),use_container_width=True)
        if tmp.delay_reason.fillna("").ne("").any():
            reasons=tmp[tmp.delay_reason.fillna("")!=""].groupby("delay_reason",as_index=False).size()
            st.plotly_chart(px.bar(reasons,x="delay_reason",y="size",title="Recorded delay reasons"),use_container_width=True)
        download_csv(tmp,"Delivery Report","delivery_csv")
    st.subheader("Add delivery")
    with st.form("delivery_add"):
        order_id=st.text_input("Order ID",value=f"ORD-{date.today():%y%m%d}-{random.randint(100,999)}")
        order_date=st.date_input("Order date",value=date.today())
        promised=st.text_input("Promised datetime",placeholder="2026-10-28 18:30")
        delivered_at=st.text_input("Delivered datetime",placeholder="2026-10-28 18:45")
        area=st.text_input("Area / route zone")
        km=st.number_input("Distance km",min_value=0.0,value=0.0)
        fee=st.number_input("Delivery fee ₹",min_value=0.0,value=0.0)
        driver=st.text_input("Driver / courier")
        status=st.selectbox("Status",["Pending","Preparing","Out for delivery","Delivered","Cancelled","Failed"])
        value=st.number_input("Order value ₹",min_value=0.0,value=0.0)
        items=st.text_input("Item summary")
        rating=st.slider("Customer rating (0 = not rated)",0,5,0)
        reason=st.text_input("Delay / failure reason")
        notes=st.text_input("Notes")
        if st.form_submit_button("Save delivery"):
            run("""INSERT INTO deliveries(order_id,order_date,promised_at,delivered_at,area,distance_km,delivery_fee,driver,status,order_value,item_summary,customer_rating,delay_reason,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(order_id,order_date.isoformat(),promised or None,delivered_at or None,area,km,fee,driver,status,value,items,rating or None,reason,notes))
            audit("CREATE","delivery",order_id,status)
            st.success("Delivery saved."); st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# 12. WEATHER / FESTIVAL / CONTEXT DIARY
# ─────────────────────────────────────────────────────────────────────────────
elif page=="Weather & Festival Diary":
    heading("Weather & Festival Diary","Capture possible demand drivers consistently; no automatic API is assumed.")
    st.caption("Record verified local weather. Festival dates vary by year and location; check a trusted local calendar.")
    with st.form("context_entry"):
        day=st.date_input("Date",value=date.today())
        c1,c2,c3=st.columns(3)
        maxt=c1.number_input("Maximum °C",value=32.0,step=0.5)
        mint=c2.number_input("Minimum °C",value=24.0,step=0.5)
        rain=c3.number_input("Rainfall mm",min_value=0.0,value=0.0)
        c4,c5,c6=st.columns(3)
        humidity=c4.number_input("Humidity %",min_value=0,max_value=100,value=60)
        holiday=c5.checkbox("Public / school holiday")
        school=c6.checkbox("School open",value=True)
        festival=st.text_input("Festival / occasion")
        event=st.text_input("Local event, fair, match")
        promotion=st.text_input("Promotion active")
        competitor=st.text_input("Competitor / market note")
        footfall=st.number_input("Estimated footfall",min_value=0,value=0)
        stockout=st.text_input("Products unavailable / stockout")
        source=st.text_input("Weather source / station")
        notes=st.text_input("Other notes")
        if st.form_submit_button("Save daily context"):
            run("""INSERT OR REPLACE INTO daily_context(day,max_temp_c,min_temp_c,rainfall_mm,humidity_pct,festival,holiday,school_open,local_event,promotion,competitor_note,footfall,stockout_products,weather_source,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(day.isoformat(),maxt,mint,rain,humidity,festival,int(holiday),int(school),event,promotion,competitor,footfall or None,stockout,source,notes))
            audit("UPSERT","daily_context",day.isoformat())
            st.success("Context saved."); st.rerun()
    cx=load_context()
    if not cx.empty:
        st.subheader("Context table")
        st.dataframe(cx,use_container_width=True,hide_index=True)
        daily=add_context_features(filtered)
        if not daily.empty and "max_temp_c" in daily:
            a,b=st.columns(2)
            a.plotly_chart(px.scatter(daily,x="max_temp_c",y="revenue",hover_data=["day"],title="Maximum temperature vs sales"),use_container_width=True)
            b.plotly_chart(px.scatter(daily,x="rainfall_mm",y="revenue",hover_data=["day"],title="Rainfall vs sales"),use_container_width=True)
        download_csv(cx,"Daily Context","context_csv")

# ─────────────────────────────────────────────────────────────────────────────
# 13. SALES ENTRY AND IMPORT
# ─────────────────────────────────────────────────────────────────────────────
elif page=="Sales Entry & Imports":
    heading("Sales Entry & Imports","Enter transactions or load a CSV export from your POS.")
    tab1,tab2=st.tabs(["Add a sale","CSV import"])
    with tab1:
        with st.form("sale_entry"):
            sold_day=st.date_input("Sale date",value=date.today())
            sold_time=st.time_input("Sale time",value=datetime.now().time().replace(second=0,microsecond=0))
            pname=st.selectbox("Product",products.name.tolist() if not products.empty else [])
            qty=st.number_input("Quantity",min_value=0.01,value=1.0,step=0.5)
            default_price=float(products.loc[products.name==pname,"selling_price"].iloc[0]) if pname and not products.empty else 0.0
            price=st.number_input("Unit selling price ₹",min_value=0.0,value=default_price)
            discount=st.number_input("Discount ₹",min_value=0.0,value=0.0)
            channel=st.selectbox("Channel",["Walk-in","WhatsApp","Phone","Online","Delivery","Catering","Wholesale"])
            customer_code=st.text_input("Customer code (optional)")
            order=st.text_input("Order ID")
            payment=st.selectbox("Payment method",["UPI","Cash","Card","Online","Credit"])
            promo=st.text_input("Promotion")
            occasion=st.text_input("Occasion / festival")
            notes=st.text_input("Notes (avoid sensitive personal data)")
            if st.form_submit_button("Save sale") and pname:
                pid=int(products.loc[products.name==pname,"id"].iloc[0]); cid=None
                if customer_code:
                    c=q("SELECT id FROM customers WHERE customer_code=?",(customer_code,))
                    if c.empty: st.error("Customer code not found. Add the customer first.")
                    else: cid=int(c.id.iloc[0])
                if not customer_code or cid:
                    run("""INSERT INTO sales(sold_at,product_id,quantity,unit_price,discount,channel,customer_id,order_id,payment_method,promotion,occasion,notes)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(datetime.combine(sold_day,sold_time).isoformat(sep=" "),pid,qty,price,discount,channel,cid,order,payment,promo,occasion,notes))
                    audit("CREATE","sale",order,f"{pname} x {qty}")
                    st.success("Sale recorded."); st.rerun()
    with tab2:
        st.markdown("Required columns: `sold_at, product, quantity, unit_price`. Optional: `discount, channel, customer_code, order_id, payment_method, promotion, occasion, notes`.")
        uploaded=st.file_uploader("Choose sales CSV",type=["csv"])
        if uploaded:
            try:
                imp=pd.read_csv(uploaded)
                st.dataframe(imp.head(15),use_container_width=True)
                required={"sold_at","product","quantity","unit_price"}
                if not required.issubset(imp.columns):
                    st.error("Missing required columns: "+", ".join(sorted(required-set(imp.columns))))
                elif st.button("Import rows shown above"):
                    ok=0; errors=[]
                    for ix,row in imp.iterrows():
                        pr=q("SELECT id FROM products WHERE name=?",(str(row["product"]),))
                        if pr.empty: errors.append(f"Row {ix+2}: product not found: {row['product']}"); continue
                        cid=None; code=str(row.get("customer_code","")).strip()
                        if code and code.lower()!="nan":
                            c=q("SELECT id FROM customers WHERE customer_code=?",(code,))
                            if not c.empty: cid=int(c.id.iloc[0])
                        try:
                            run("""INSERT INTO sales(sold_at,product_id,quantity,unit_price,discount,channel,customer_id,order_id,payment_method,promotion,occasion,notes)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(str(row["sold_at"]),int(pr.id.iloc[0]),float(row["quantity"]),float(row["unit_price"]),float(row.get("discount",0) or 0),str(row.get("channel","Walk-in")),cid,str(row.get("order_id","")),str(row.get("payment_method","UPI")),str(row.get("promotion","")),str(row.get("occasion","")),str(row.get("notes",""))))
                            ok+=1
                        except Exception as exc: errors.append(f"Row {ix+2}: {exc}")
                    st.success(f"Imported {ok} rows.")
                    if errors: st.warning("Skipped rows:"); st.write(errors[:50])
            except Exception as exc:
                st.error(f"Could not read this CSV: {exc}")

# ─────────────────────────────────────────────────────────────────────────────
# 14. CATALOG AND CUSTOMER CRM
# ─────────────────────────────────────────────────────────────────────────────
elif page=="Catalog & Customer CRM":
    heading("Catalog & Customer CRM","Maintain products and minimal customer records responsibly.")
    tab1,tab2,tab3=st.tabs(["Products","Add product","Customers"])
    with tab1:
        st.dataframe(products,use_container_width=True,hide_index=True)
        download_csv(products,"Product Catalog","catalog_csv")
    with tab2:
        with st.form("product_add"):
            sku=st.text_input("SKU")
            name=st.text_input("Product name")
            category=st.selectbox("Category",["Premium Sweets","Milk Sweets","Bengali Sweets","Laddu","Dry Sweets","Hot Sweets","Snacks","Fusion Sweets","Gift Boxes","Bakery","Beverage","Other"])
            unit=st.selectbox("Sales unit",["piece","kg","box","packet","litre"])
            price=st.number_input("Selling price ₹",min_value=0.0,value=100.0)
            cost=st.number_input("Estimated unit cost ₹",min_value=0.0,value=50.0)
            shelf=st.number_input("Shelf life days",min_value=1,value=3)
            reorder=st.number_input("Reorder threshold",min_value=0.0,value=5.0)
            supplier=st.text_input("Supplier")
            if st.form_submit_button("Add product"):
                try:
                    run("INSERT INTO products(sku,name,category,unit,selling_price,unit_cost,shelf_life_days,reorder_level,supplier) VALUES(?,?,?,?,?,?,?,?,?)",
                        (sku or None,name.strip(),category,unit,price,cost,int(shelf),reorder,supplier))
                    audit("CREATE","product",sku or name)
                    st.success("Product created."); st.rerun()
                except Exception as exc: st.error(str(exc))
    with tab3:
        st.dataframe(customers.drop(columns=["phone"],errors="ignore"),use_container_width=True,hide_index=True)
        st.caption("Phone numbers are personal data. Keep them private and export only when necessary.")
        st.subheader("Add customer")
        with st.form("customer_add"):
            code=st.text_input("Unique customer code",value=f"C{random.randint(1000,9999)}")
            display=st.text_input("Display name")
            phone=st.text_input("Phone (optional)")
            area=st.text_input("Area")
            segment=st.selectbox("Segment",["Regular","Family","Office","Event","New","Wholesale"])
            consent=st.checkbox("Explicit consent for marketing messages")
            if st.form_submit_button("Save customer"):
                try:
                    run("INSERT INTO customers(customer_code,display_name,phone,area,segment,marketing_consent) VALUES(?,?,?,?,?,?)",(code,display,phone,area,segment,int(consent)))
                    audit("CREATE","customer",code)
                    st.success("Customer created."); st.rerun()
                except Exception as exc: st.error(str(exc))

# ─────────────────────────────────────────────────────────────────────────────
# 15. PROMOTION TRACKING
# ─────────────────────────────────────────────────────────────────────────────
elif page=="Promotions & Experiments":
    heading("Promotions & Experiments","Record campaigns and compare performance without confusing correlation with causation.")
    promo_df=q("SELECT * FROM promotions ORDER BY start_date DESC")
    st.dataframe(promo_df,use_container_width=True,hide_index=True)
    with st.form("promo_add"):
        name=st.text_input("Campaign name")
        start=st.date_input("Start date",value=date.today())
        end=st.date_input("End date",value=date.today()+timedelta(days=7))
        pct=st.number_input("Discount %",min_value=0.0,max_value=100.0,value=10.0)
        channel=st.selectbox("Channel",["All","Walk-in","WhatsApp","Online","Delivery","Catering"])
        spend=st.number_input("Campaign spend ₹",min_value=0.0,value=0.0)
        notes=st.text_input("Hypothesis / notes")
        if st.form_submit_button("Save campaign"):
            if end<start: st.error("End date must not be before start date.")
            else:
                run("INSERT INTO promotions(name,start_date,end_date,discount_pct,channel,spend,notes) VALUES(?,?,?,?,?,?,?)",
                    (name,start.isoformat(),end.isoformat(),pct,channel,spend,notes))
                audit("CREATE","promotion",name)
                st.success("Campaign saved."); st.rerun()
    if not filtered.empty:
        st.subheader("Observed promotion performance")
        observed=filtered.assign(promo_group=filtered.promotion.fillna("").replace("","No promotion"))
        report=observed.groupby("promo_group",as_index=False).agg(revenue=("revenue","sum"),quantity=("quantity","sum"),transactions=("id","count"))
        st.dataframe(report,use_container_width=True,hide_index=True)
        st.caption("This comparison is observational. For a stronger estimate, predefine a test/control design and compare similar days, products, channels and stock availability.")

# ─────────────────────────────────────────────────────────────────────────────
# 16. REPORTS AND DATA QUALITY
# ─────────────────────────────────────────────────────────────────────────────
elif page=="Reports & Data Quality":
    heading("Reports & Data Quality","Export records, check consistency and spot data gaps.")
    tables=["products","customers","sales","daily_context","stock_movements","ingredients","recipes","deliveries","suppliers","promotions"]
    counts=[]
    for table in tables:
        counts.append({"table":table,"rows":int(q(f"SELECT COUNT(*) AS n FROM {table}").iloc[0,0])})
    st.dataframe(pd.DataFrame(counts),use_container_width=True,hide_index=True)
    checks=[
        ("Sales with non-positive quantity",int(q("SELECT COUNT(*) n FROM sales WHERE quantity<=0").iloc[0,0])),
        ("Products with price below cost",int(q("SELECT COUNT(*) n FROM products WHERE selling_price<unit_cost").iloc[0,0])),
        ("Sales without order ID",int(q("SELECT COUNT(*) n FROM sales WHERE order_id IS NULL OR order_id=''").iloc[0,0])),
        ("Context missing max temperature",int(q("SELECT COUNT(*) n FROM daily_context WHERE max_temp_c IS NULL").iloc[0,0])),
        ("Customers without marketing consent",int(q("SELECT COUNT(*) n FROM customers WHERE marketing_consent=0").iloc[0,0])),
    ]
    st.subheader("Quality checks")
    st.dataframe(pd.DataFrame(checks,columns=["Check","Count"]),use_container_width=True,hide_index=True)
    st.subheader("Filtered sales detail")
    st.dataframe(filtered,use_container_width=True,hide_index=True)
    download_csv(filtered,"Filtered Sales","filtered_sales_csv")
    for table in tables:
        data=q(f"SELECT * FROM {table}")
        st.download_button(f"Export {table}.csv",data.to_csv(index=False).encode("utf-8"),file_name=f"{table}.csv",mime="text/csv",key=f"export_{table}")

# ─────────────────────────────────────────────────────────────────────────────
# 17. SETTINGS, BACKUP AND SAFE DEPLOYMENT NOTES
# ─────────────────────────────────────────────────────────────────────────────
elif page=="Settings & Data Export":
    heading("Settings & Data Export","Backups, demo-data controls and deployment notes.")
    st.write("**Database path:**",str(DB_FILE.resolve()))
    st.write("**Demo seeding setting:**",os.getenv("SWEETSHOP_DEMO","1"))
    if DB_FILE.exists():
        st.download_button("Download SQLite database backup",DB_FILE.read_bytes(),file_name="sweetshop_ai_os_backup.db",mime="application/octet-stream")
    st.subheader("Audit log")
    log=q("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 250")
    st.dataframe(log,use_container_width=True,hide_index=True)
    st.subheader("Important deployment checklist")
    st.markdown("""
- This single-file prototype is suitable for local testing and a private demo, not an exposed public production service.
- Add authentication, role-based access, HTTPS, encrypted backups, secrets management and an appropriate hosted database before multi-user deployment.
- Never commit the live SQLite database, customer phone numbers, credentials, API keys or real transaction exports to GitHub.
- Set `SWEETSHOP_DEMO=0` to prevent automatic demo seeding on a fresh database. Existing demo rows must be removed separately if you already ran the app.
- Weather is entered manually in this version. Add a licensed/reliable weather provider and local festival calendar only after configuring API credentials and validating location/time zone.
- Current demand models use a limited set of calendar and recorded weather features. Add explicit festival encoding, stockout correction, holiday calendars and more history before treating results as operational forecasts.
- Stock is calculated from movement records. Sales do not automatically deduct inventory; connect sales, recipes, production batches and wastage in a tested transaction workflow before relying on stock counts.
- Profit estimates use current catalog cost and exclude GST, overhead, labour, packaging, waste and delivery expense.
- Follow applicable privacy and consumer-protection rules. Collect only necessary data and honour marketing consent.
""")
    st.subheader("Environment variables")
    st.code("SWEETSHOP_DEMO=0\nSWEETSHOP_DB=/path/to/private/sweetshop.db",language="bash")

st.divider()
st.caption("SweetShop AI OS • Prototype • Predictions should be validated against real outcomes before operational decisions.")
