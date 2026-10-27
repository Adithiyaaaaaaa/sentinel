-- Fictional schema; no real customer or payment information.
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    account TEXT NOT NULL UNIQUE
);

CREATE TABLE payments (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    account TEXT NOT NULL,
    amount INTEGER NOT NULL,
    refunded INTEGER NOT NULL DEFAULT 0
);
