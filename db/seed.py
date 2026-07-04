"""
Creates and seeds the ecommerce.db SQLite database with realistic sample data.
Run: python db/seed.py
"""
import sqlite3                             # create/populate the SQLite file directly (no ORM)
import random                              # deterministic pseudo-random sampling (seeded below)
import os                                  # unused directly, kept for parity with other entry scripts
from datetime import datetime, timedelta   # generate random-but-bounded order/review/signup dates
from pathlib import Path                   # locate the DB file relative to this script, not the cwd

DB_PATH = Path(__file__).parent / "ecommerce.db"   # always db/ecommerce.db, regardless of cwd

# (name, category, price, stock_quantity) — 50 fixed products across 5 categories,
# used verbatim as INSERT values in seed() below.
PRODUCTS = [
    ("iPhone 15 Pro", "Electronics", 999.99, 50),
    ("Samsung Galaxy S24", "Electronics", 849.99, 75),
    ("MacBook Air M3", "Electronics", 1299.99, 30),
    ("Dell XPS 15", "Electronics", 1199.99, 25),
    ("Sony WH-1000XM5", "Electronics", 349.99, 100),
    ("iPad Pro 12.9", "Electronics", 1099.99, 40),
    ("Apple Watch Ultra 2", "Electronics", 799.99, 60),
    ("Google Pixel 8", "Electronics", 699.99, 45),
    ("Nintendo Switch OLED", "Electronics", 349.99, 80),
    ("PS5 DualSense Controller", "Electronics", 69.99, 150),
    ("Levi's 501 Jeans", "Clothing", 59.99, 200),
    ("Nike Air Force 1", "Clothing", 89.99, 150),
    ("Adidas Ultraboost 22", "Clothing", 179.99, 100),
    ("The North Face Jacket", "Clothing", 249.99, 75),
    ("Polo Ralph Lauren Shirt", "Clothing", 89.99, 120),
    ("Lululemon Leggings", "Clothing", 98.00, 90),
    ("Ray-Ban Aviator Sunglasses", "Clothing", 154.00, 60),
    ("Champion Hoodie", "Clothing", 44.99, 200),
    ("Converse Chuck Taylor", "Clothing", 55.00, 180),
    ("Columbia Rain Jacket", "Clothing", 139.99, 85),
    ("Atomic Habits", "Books", 16.99, 300),
    ("The Pragmatic Programmer", "Books", 49.99, 150),
    ("Clean Code", "Books", 44.99, 120),
    ("Designing Data-Intensive Applications", "Books", 54.99, 100),
    ("The Psychology of Money", "Books", 14.99, 250),
    ("Deep Work", "Books", 15.99, 200),
    ("Zero to One", "Books", 13.99, 180),
    ("The Lean Startup", "Books", 17.99, 160),
    ("Thinking Fast and Slow", "Books", 16.99, 140),
    ("Sapiens", "Books", 15.99, 190),
    ("Instant Pot Duo 7-in-1", "Home & Kitchen", 99.99, 80),
    ("Dyson V15 Vacuum", "Home & Kitchen", 649.99, 30),
    ("KitchenAid Stand Mixer", "Home & Kitchen", 399.99, 25),
    ("Nespresso Vertuo Machine", "Home & Kitchen", 169.99, 60),
    ("Vitamix Blender", "Home & Kitchen", 449.99, 20),
    ("iRobot Roomba i7", "Home & Kitchen", 299.99, 40),
    ("Philips Air Fryer XL", "Home & Kitchen", 119.99, 70),
    ("Le Creuset Dutch Oven", "Home & Kitchen", 369.99, 15),
    ("Bose Smart Speaker", "Home & Kitchen", 299.99, 50),
    ("Cuisinart Coffee Maker", "Home & Kitchen", 79.99, 90),
    ("Bowflex SelectTech Dumbbells", "Sports", 349.99, 40),
    ("TRX Suspension Trainer", "Sports", 189.99, 60),
    ("Garmin Forerunner 965", "Sports", 599.99, 35),
    ("Yeti Tundra 45 Cooler", "Sports", 299.99, 50),
    ("Wilson Pro Staff Tennis Racket", "Sports", 79.99, 100),
    ("Callaway Edge Golf Set", "Sports", 899.99, 20),
    ("Hydro Flask 32oz", "Sports", 44.95, 200),
    ("Manduka PRO Yoga Mat", "Sports", 88.00, 120),
    ("Rogue Ohio Barbell", "Sports", 295.00, 25),
    ("NordicTrack Treadmill", "Sports", 1499.99, 15),
]

# (city, country) pairs — sampled per customer to give the dataset international spread.
LOCATIONS = [
    ("Mumbai", "India"), ("Delhi", "India"), ("Bangalore", "India"),
    ("Hyderabad", "India"), ("Chennai", "India"), ("Pune", "India"),
    ("Kolkata", "India"), ("Ahmedabad", "India"),
    ("New York", "USA"), ("Los Angeles", "USA"), ("Chicago", "USA"),
    ("Houston", "USA"), ("San Francisco", "USA"), ("Seattle", "USA"),
    ("London", "UK"), ("Manchester", "UK"), ("Birmingham", "UK"),
    ("Toronto", "Canada"), ("Vancouver", "Canada"),
    ("Sydney", "Australia"), ("Melbourne", "Australia"),
    ("Singapore", "Singapore"), ("Dubai", "UAE"), ("Berlin", "Germany"),
]

SEGMENTS = ["Premium", "Standard", "Basic"]   # random.choice() gives each segment equal weight
# "completed" repeated 3x so random.choice() weights outcomes toward completed orders,
# without needing random.choices()'s separate weights argument here.
STATUSES = ["completed", "completed", "completed", "shipped", "pending", "cancelled"]

# First/last names combined via random.choice() x random.choice() to build 150 customer names —
# mixing Indian and Western names to match the LOCATIONS spread above.
FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Rohan", "Raj",
    "Priya", "Divya", "Anjali", "Pooja", "Sneha", "Isha", "Meera", "Nisha",
    "James", "John", "Michael", "David", "Sarah", "Emily", "Emma", "Olivia",
    "Liam", "Noah", "William", "Lucas", "Ethan", "Sophia", "Isabella", "Mia",
    "Rahul", "Vikram", "Suresh", "Amit", "Ravi", "Deepak", "Sachin", "Nikhil",
]

LAST_NAMES = [   # paired with FIRST_NAMES; index positions have no relationship to each other
    "Sharma", "Patel", "Singh", "Kumar", "Gupta", "Verma", "Shah", "Mehta",
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson", "White",
    "Reddy", "Nair", "Pillai", "Iyer", "Joshi", "Rao", "Mishra", "Sinha",
]


def random_date(start: datetime, end: datetime) -> str:
    """Pick a uniformly random date between start and end, formatted as YYYY-MM-DD."""
    delta = end - start                                          # total span to sample within
    seconds_offset = random.randint(0, int(delta.total_seconds()))  # random point inside that span
    return (start + timedelta(seconds=seconds_offset)).strftime("%Y-%m-%d")


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all five tables (idempotent — IF NOT EXISTS) with their FK relationships."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS customers (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            email           TEXT UNIQUE NOT NULL,
            city            TEXT NOT NULL,
            country         TEXT NOT NULL,
            signup_date     TEXT NOT NULL,
            segment         TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS products (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            category        TEXT NOT NULL,
            price           REAL NOT NULL,
            stock_quantity  INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS orders (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id     INTEGER NOT NULL REFERENCES customers(id),
            order_date      TEXT NOT NULL,
            status          TEXT NOT NULL,
            total_amount    REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id        INTEGER NOT NULL REFERENCES orders(id),
            product_id      INTEGER NOT NULL REFERENCES products(id),
            quantity        INTEGER NOT NULL,
            unit_price      REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id     INTEGER NOT NULL REFERENCES customers(id),
            product_id      INTEGER NOT NULL REFERENCES products(id),
            rating          INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            review_date     TEXT NOT NULL
        );
    """)


def seed(conn: sqlite3.Connection) -> None:
    """Populate all five tables with interrelated fake data (150 customers, 50 products, ...)."""
    random.seed(42)                             # fixed seed → same "random" dataset on every reseed
    start_date = datetime(2023, 1, 1)           # earliest possible signup/order/review date
    end_date = datetime(2024, 12, 31)           # latest possible signup/order/review date

    # ── Customers ────────────────────────────────────────────────────────────
    customers = []
    for i in range(150):
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"        # random first+last combo
        email = f"{name.lower().replace(' ', '.')}{i}@example.com"               # i keeps emails unique even with duplicate names
        city, country = random.choice(LOCATIONS)                                  # one random (city, country) pair
        signup_date = random_date(start_date, end_date)
        segment = random.choice(SEGMENTS)
        customers.append((name, email, city, country, signup_date, segment))       # tuple matches the INSERT column order below

    conn.executemany(
        "INSERT INTO customers (name, email, city, country, signup_date, segment) VALUES (?,?,?,?,?,?)",
        customers,
    )

    # ── Products ─────────────────────────────────────────────────────────────
    # Fixed catalogue (no randomness) — inserted as-is from the PRODUCTS constant above.
    conn.executemany(
        "INSERT INTO products (name, category, price, stock_quantity) VALUES (?,?,?,?)",
        PRODUCTS,
    )

    # ── Orders + order_items ─────────────────────────────────────────────────
    order_rows = []                    # (customer_id, date, status, total, [line items]) per order
    item_rows = []                     # flattened (order_id, product_id, qty, price) rows for the final bulk insert
    num_products = len(PRODUCTS)       # product IDs run 1..num_products (SQLite AUTOINCREMENT starts at 1)

    for customer_id in range(1, 151):                 # every customer places 1-8 orders
        num_orders = random.randint(1, 8)
        for _ in range(num_orders):
            order_date = random_date(start_date, end_date)
            status = random.choice(STATUSES)
            items_count = random.randint(1, 4)          # each order has 1-4 distinct line items
            # sample() avoids picking the same product twice within one order
            selected_products = random.sample(range(1, num_products + 1), min(items_count, num_products))
            total = 0.0
            order_items_temp = []
            for pid in selected_products:
                qty = random.randint(1, 3)              # 1-3 units of this product in the order
                price = PRODUCTS[pid - 1][2]             # PRODUCTS is 0-indexed, product IDs are 1-indexed
                total += qty * price                     # running order total, used for orders.total_amount
                order_items_temp.append((pid, qty, price))
            # order_items_temp is carried alongside the order row until we know its real order_id below
            order_rows.append((customer_id, order_date, status, round(total, 2), order_items_temp))

    for order_idx, (cid, odate, ostatus, ototal, oitems) in enumerate(order_rows):
        conn.execute(
            "INSERT INTO orders (customer_id, order_date, status, total_amount) VALUES (?,?,?,?)",
            (cid, odate, ostatus, ototal),
        )
        order_id = order_idx + 1     # mirrors AUTOINCREMENT since orders are inserted in this exact order, 1-based
        for pid, qty, price in oitems:
            item_rows.append((order_id, pid, qty, price))   # now that order_id is known, flatten into the final insert list

    conn.executemany(
        "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?,?,?,?)",
        item_rows,
    )

    # ── Reviews ──────────────────────────────────────────────────────────────
    review_rows = []
    for customer_id in range(1, 151):
        num_reviews = random.randint(0, 5)     # some customers leave zero reviews
        reviewed_products = random.sample(range(1, num_products + 1), min(num_reviews, num_products))
        for pid in reviewed_products:
            # Weighted toward high ratings (4-5 stars far more likely than 1-2) — mirrors real review skew
            rating = random.choices([1, 2, 3, 4, 5], weights=[5, 10, 15, 35, 35])[0]
            review_date = random_date(start_date, end_date)
            review_rows.append((customer_id, pid, rating, review_date))

    conn.executemany(
        "INSERT INTO reviews (customer_id, product_id, rating, review_date) VALUES (?,?,?,?)",
        review_rows,
    )

    conn.commit()   # persist everything in one transaction — nothing above is durable until this line


def main() -> None:
    """Recreate the database from scratch and print row counts as a sanity check."""
    if DB_PATH.exists():
        DB_PATH.unlink()   # delete any existing DB so this script is safely re-runnable

    conn = sqlite3.connect(DB_PATH)
    create_schema(conn)   # tables first...
    seed(conn)            # ...then fill them

    # Quick verification — confirms every table actually got rows before declaring success
    for table in ["customers", "products", "orders", "order_items", "reviews"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count} rows")

    conn.close()
    print(f"\nDatabase created at: {DB_PATH}")


if __name__ == "__main__":
    main()   # only run when invoked directly (`python db/seed.py`), not on import
